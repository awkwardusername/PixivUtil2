#!/usr/bin/python
# -*- coding: UTF-8 -*-
import sys
import os
import re
import traceback
import logging
import logging.handlers
import gc
import time
import xml.sax.saxutils as saxutils
import datetime

from mechanize import Browser
import mechanize
from BeautifulSoup import BeautifulSoup, Tag
import urllib2
import urllib

import getpass
import socket
import httplib
import cookielib

import PixivConstant
import PixivConfig
import PixivDBManager
import PixivHelper
from PixivModel import PixivArtist, PixivImage, PixivListItem, PixivBookmark, PixivTags, PixivNewIllustBookmark, PixivGroup
from PixivException import PixivException
import PixivBrowserFactory

script_path = PixivHelper.module_path()

Yavos = True
npisvalid = False
np = 0
opisvalid = False
op = ''

from optparse import OptionParser
import datetime
import codecs
import subprocess

gc.enable()
##gc.set_debug(gc.DEBUG_LEAK)

__dbManager__ = PixivDBManager.PixivDBManager()
__config__    = PixivConfig.PixivConfig()
__br__        = None ##PixivBrowserFactory.getBrowser(config=__config__)
__blacklistTags = list()
__suppressTags = list()
__log__ = PixivHelper.GetLogger()

## http://www.pixiv.net/member_illust.php?mode=medium&illust_id=18830248
__re_illust = re.compile(r'member_illust.*illust_id=(\d*)')
__re_manga_page = re.compile('(\d+(_big)?_p\d+)')

### Utilities function ###
def clearall():
    all = [var for var in globals() if (var[:2], var[-2:]) != ("__", "__") and var != "clearall"]
    for var in all:
        del globals()[var]

def customRequest(url):
    if __config__.useProxy:
        proxy = urllib2.ProxyHandler(__config__.proxy)
        opener = urllib2.build_opener(proxy)
        urllib2.install_opener(opener)
    req = urllib2.Request(url)
    return req

#-T04------For download file
def downloadImage(url, filename, referer, overwrite, retry, backupOldFile=False):
    try:
        try:
            req = customRequest(url)

            if referer != None:
                req.add_header('Referer', referer)
            else :
                req.add_header('Referer', 'http://www.pixiv.net')

            print "Using Referer:", str(referer)
            filesize = -1

            print 'Start downloading...',
            startTime = datetime.datetime.now()
            res = __br__.open_novisit(req)
            try:
                filesize = int(res.info()['Content-Length'])
            except KeyError:
                filesize = -1
                print "\tNo file size information!"
            except:
                raise

            if os.path.exists(filename) and os.path.isfile(filename) :
                oldSize = os.path.getsize(filename)
                if not overwrite and int(filesize) == oldSize :
                    print "\tFile exist! (Identical Size)"
                    return 0 #Yavos: added 0 -> updateImage() will be executed
                else :
                    if backupOldFile:
                        splitName = filename.rsplit(".", 1)
                        newName = filename + "." + str(int(time.time()))
                        if len(splitName) == 2:
                            newName = splitName[0] + "." + str(int(time.time())) + "." + splitName[1]
                        PixivHelper.safePrint("\t Found file with different filesize, backing up to: " + newName)
                        __log__.info("Found file with different filesize, backing up to: " + newName)
                        os.rename(filename, newName)
                    else:
                        print "\t Found file with different filesize, removing..."
                        __log__.info("Found file with different filesize, removing old file (old: " + str(oldSize) + " vs new: " + str(filesize) + ")")
                        os.remove(filename)

            directory = os.path.dirname(filename)
            if not os.path.exists(directory):
                __log__.info('Creating directory: '+directory)
                os.makedirs(directory)

            try:
                save = file(filename + '.pixiv', 'wb+', 4096)
            except IOError:
                msg = 'Error at downloadImage(): Cannot save ' + url +' to ' + filename + ' ' + str(sys.exc_info())
                PixivHelper.safePrint(msg)
                __log__.error(unicode(msg))
                filename = os.path.split(url)[1]
                filename = filename.split("?")[0]
                filename = PixivHelper.sanitizeFilename(filename)
                save = file(filename + '.pixiv', 'wb+', 4096)
                msg2 = 'File is saved to ' + filename
                __log__.info(msg2)

            prev = 0
            curr = 0

            print '{0:22} Bytes'.format(prev),
            try:
                while 1:
                    save.write(res.read(PixivConstant.BUFFER_SIZE))
                    curr = save.tell()
                    print '\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b',
                    print '{0:9} of {1:9} Bytes'.format(curr, filesize),

                    ## check if downloaded file is complete
                    if filesize > 0 and curr == filesize:
                        totalTime = (datetime.datetime.now() - startTime).total_seconds()
                        print ' Completed in ' + str(totalTime) + 's (' + PixivHelper.speedInStr(filesize, totalTime) + ')'
                        break
                    elif curr == prev:  ## no filesize info
                        totalTime = (datetime.datetime.now() - startTime).total_seconds()
                        print ' Completed in ' + str(totalTime) + 's (' + PixivHelper.speedInStr(curr, totalTime) + ')'
                        break
                    prev = curr
                if iv == True or __config__.createDownloadLists == True:
                    dfile = codecs.open(dfilename, 'a+', encoding='utf-8')
                    dfile.write(filename + "\n")
                    dfile.close()
            except:
                if filesize > 0 and curr < filesize:
                    PixivHelper.printAndLog('error', 'Downloaded file incomplete! {0:9} of {1:9} Bytes'.format(curr, filesize))
                    PixivHelper.printAndLog('error', 'Filename = ' + unicode(filename))
                    PixivHelper.printAndLog('error', 'URL      = {0}'.format(url))
                raise
            finally:
                save.close()
                if overwrite and os.path.exists(filename):
                    os.remove(filename)
                os.rename(filename + '.pixiv', filename)
                del save
                del req
                del res
        except urllib2.HTTPError as httpError:
            PixivHelper.printAndLog('error', '[downloadImage()] ' + str(httpError) + ' (' + url + ')')
            if httpError.code == 404:
                return -1
            if httpError.code == 502:
                return -1
            raise
        except urllib2.URLError as urlError:
            PixivHelper.printAndLog('error', '[downloadImage()] ' + str(urlError) + ' (' + url + ')')
            raise
        except IOError as ioex:
            if ioex.errno == 28:
                PixivHelper.printAndLog('error', ioex.message)
                raw_input("Press Enter to retry.");
                return -1
            raise
        except KeyboardInterrupt:
            PixivHelper.printAndLog('info', 'Aborted by user request => Ctrl-C')
            raise
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback)
            __log__.exception('Error at downloadImage(): ' + str(sys.exc_info()) + '(' + url + ')')
            raise
    except KeyboardInterrupt:
        raise
    except:
        if retry > 0:
            repeat = range(1,__config__.retryWait)
            for t in repeat:
                print t,
                time.sleep(1)
            print ''
            return downloadImage(url, filename, referer, overwrite, retry - 1)
        else :
            raise
    print ' done.'
    return 0

def loadCookie(cookieValue):
    '''Load cookie to the Browser instance'''
    ck = cookielib.Cookie(version=0, name='PHPSESSID', value=cookieValue, port=None, port_specified=False, domain='pixiv.net', domain_specified=False, domain_initial_dot=False, path='/', path_specified=True, secure=False, expires=None, discard=True, comment=None, comment_url=None, rest={'HttpOnly': None}, rfc2109=False)
    PixivBrowserFactory.addCookie(ck)

### Pixiv related function ###
def pixivLoginCookie():
    '''Log in to Pixiv using saved cookie, return True if success'''

    PixivHelper.printAndLog('info','logging in with saved cookie')
    cookieValue = __config__.cookie
    if len(cookieValue) > 0:
        PixivHelper.printAndLog('info','Trying to log with saved cookie')
        loadCookie(cookieValue);
        req = customRequest('http://www.pixiv.net/mypage.php')
        __br__.open(req)
        resUrl = __br__.response().geturl()
        if resUrl == 'http://www.pixiv.net/mypage.php' :
            print 'done.'
            __log__.info('Logged in using cookie')
            return True
        else :
            __log__.info('Failed to login using cookie, returned page: ' + resUrl)
            PixivHelper.printAndLog('info','Cookie already expired/invalid.')
    return False

def pixivLogin(username, password):
    '''Log in to Pixiv, return 0 if success'''

    try:
        PixivHelper.printAndLog('info','Log in using form.')
        req = customRequest(PixivConstant.PIXIV_URL+PixivConstant.PIXIV_LOGIN_URL)
        __br__.open(req)

        form = __br__.select_form(nr=PixivConstant.PIXIV_FORM_NUMBER)
        __br__['pixiv_id'] = username
        __br__['pass'] = password
        if __config__.keepSignedIn:
            __br__.find_control('skip').items[0].selected = True

        response = __br__.submit()
        return pixivProcessLogin(response)
    except:
        print 'Error at pixivLogin():',sys.exc_info()
        print 'failed'
        __log__.exception('Error at pixivLogin(): ' + str(sys.exc_info()))
        raise

def pixivProcessLogin(response):
    __log__.info('Logging in, return url: ' + response.geturl())
    ## failed login will return to either of these page:
    ## http://www.pixiv.net/login.php
    ## https://www.secure.pixiv.net/login.php
    if response.geturl().find('pixiv.net/login.php') == -1:
        print 'done.'
        __log__.info('Logged in')
        ## write back the new cookie value
        for cookie in  __br__._ua_handlers['_cookies'].cookiejar:
            if cookie.name == 'PHPSESSID':
                print 'new cookie value:', cookie.value
                __config__.cookie = cookie.value
                __config__.writeConfig()
                break
        return True
    else :
        errors = parseLoginError(response)
        if len(errors)>0:
            for error in errors:
                PixivHelper.printAndLog('error','Server Reply: ' + error.string)
        else:
            PixivHelper.printAndLog('info','Wrong username or password.')
        return False

def pixivLoginSSL(username, password):
    try:
        PixivHelper.printAndLog('info','Log in using secure form.')
        req = customRequest(PixivConstant.PIXIV_URL_SSL)
        __br__.open(req)

        form = __br__.select_form(nr=PixivConstant.PIXIV_FORM_NUMBER_SSL)
        __br__['pixiv_id'] = username
        __br__['pass'] = password
        if __config__.keepSignedIn:
            __br__.find_control('skip').items[0].selected = True

        response = __br__.submit()
        return pixivProcessLogin(response)
    except:
        print 'Error at pixivLoginSSL():',sys.exc_info()
        __log__.exception('Error at pixivLoginSSL(): ' + str(sys.exc_info()))
        raise

def parseLoginError(res):
    page = BeautifulSoup(res.read())
    r = page.findAll('span', attrs={'class':'error'})
    return r

def processList(mode):
    global args
    result = None
    try:
        ## Getting the list
        if __config__.processFromDb :
            PixivHelper.printAndLog('info','Processing from database.')
            if __config__.dayLastUpdated == 0:
                result = __dbManager__.selectAllMember()
            else :
                print 'Select only last',__config__.dayLastUpdated, 'days.'
                result = __dbManager__.selectMembersByLastDownloadDate(__config__.dayLastUpdated)
        else :
            PixivHelper.printAndLog('info','Processing from list file.')
            listFilename = __config__.downloadListDirectory + os.sep + 'list.txt'
            if op == '4' and len(args) > 0:
                testListFilename = __config__.downloadListDirectory + os.sep + args[0]
                if os.path.exists(testListFilename) :
                    listFilename = testListFilename
            result = PixivListItem.parseList(listFilename, __config__.rootDirectory)
            PixivHelper.printAndLog('info','List file used: ' + listFilename)

        print "Found "+str(len(result))+" items."

        ## iterating the list
        for item in result:
            retryCount = 0
            while True:
                try:
                    processMember(mode, item.memberId, item.path)
                    break
                except KeyboardInterrupt:
                    raise
                except:
                    if retryCount > __config__.retry:
                        PixivHelper.printAndLog('error','Giving up member_id: '+str(item.memberId))
                        break
                    retryCount = retryCount + 1
                    print 'Something wrong, retrying after 2 second (', retryCount, ')'
                    time.sleep(2)

            __br__.clear_history()
            print 'done.'
    except KeyboardInterrupt:
        raise
    except:
        print 'Error at processList():',sys.exc_info()
        print 'Failed'
        __log__.exception('Error at processList(): ' + str(sys.exc_info()))
        raise

def processMember(mode, member_id, userDir='', page=1, endPage=0, bookmark=False): #Yavos added dir-argument which will be initialized as '' when not given
    PixivHelper.printAndLog('info','Processing Member Id: ' + str(member_id))
    if page != 1:
        PixivHelper.printAndLog('info', 'Start Page: ' + str(page))
    if endPage != 0:
        PixivHelper.printAndLog('info', 'End Page: ' + str(endPage))
        if __config__.numberOfPage != 0:
            PixivHelper.printAndLog('info', 'Number of page setting will be ignored')
    elif np != 0:
        PixivHelper.printAndLog('info', 'End Page from command line: ' + str(np))
    elif __config__.numberOfPage != 0:
        PixivHelper.printAndLog('info', 'End Page from config: ' + str(__config__.numberOfPage))

    __config__.loadConfig()

    try:
        noOfImages = 1
        avatarDownloaded = False
        flag = True
        updatedLimitCount = 0

        while flag:
            print 'Page ',page
            setTitle("MemberId: " + str(member_id) + " Page: " + str(page))
            ## Try to get the member page
            while True:
                try:
                    if bookmark:
                        memberUrl = 'http://www.pixiv.net/bookmark.php?id='+str(member_id)+'&p='+str(page)
                    else:
                        memberUrl = 'http://www.pixiv.net/member_illust.php?id='+str(member_id)+'&p='+str(page)
                    if __config__.r18mode:
                        memberUrl = memberUrl + '&tag=R-18'
                        PixivHelper.printAndLog('info', 'R-18 Mode only.')
                    PixivHelper.printAndLog('info', 'Member Url: ' + memberUrl)
                    listPage = __br__.open(memberUrl)
                    artist = PixivArtist(mid=member_id, page=BeautifulSoup(listPage.read()))
                    break
                except PixivException as ex:
                    PixivHelper.printAndLog('info', 'Member ID (' + str(member_id) + '): ' + str(ex))
                    if ex.errorCode == PixivException.NO_IMAGES:
                        pass
                    if ex.errorCode == PixivException.SERVER_ERROR:
                        print "Retrying... ",
                        repeat = range(1,__config__.retryWait)
                        for t in repeat:
                            print t,
                            time.sleep(1)
                        print ''
                    else:
                        PixivHelper.dumpHtml("Dump for " + str(member_id) + " Error Code " + str(ex.errorCode) + ".html", listPage.get_data())
                        if ex.errorCode == PixivException.USER_ID_NOT_EXISTS or ex.errorCode == PixivException.USER_ID_SUSPENDED:
                            __dbManager__.setIsDeletedFlagForMemberId(int(member_id))
                            PixivHelper.printAndLog('info', 'Set IsDeleted for MemberId: ' + str(member_id) + ' not exist.')
                            #__dbManager__.deleteMemberByMemberId(member_id)
                            #PixivHelper.printAndLog('info', 'Deleting MemberId: ' + str(member_id) + ' not exist.')
                        if ex.errorCode == PixivException.OTHER_MEMBER_ERROR:
                            PixivHelper.safePrint(ex.message)
                            raw_input('New Error Message, please inform the developer. Press enter to continue.')
                    return
                except AttributeError as aex:
                    # Possible layout changes, try to dump the file below
                    raise
                except Exception as ue:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    traceback.print_exception(exc_type, exc_value, exc_traceback)
                    PixivHelper.printAndLog('error', 'Error at processing Artist Info: ' + str(sys.exc_info()))
                    __log__.exception('Error at processing Artist Info: '+ str(member_id))
                    repeat = range(1,__config__.retryWait)
                    for t in repeat:
                        print t,
                        time.sleep(1)
                    print ''
            PixivHelper.safePrint('Member Name  : ' + artist.artistName)
            print 'Member Avatar:', artist.artistAvatar
            print 'Member Token :', artist.artistToken

            if artist.artistAvatar.find('no_profile') == -1 and avatarDownloaded == False and __config__.downloadAvatar :
                ## Download avatar as folder.jpg
                filenameFormat = __config__.filenameFormat
                if userDir == '':
                    targetDir = __config__.rootDirectory
                else:
                    targetDir = userDir

                avatarFilename = PixivHelper.CreateAvatarFilename(filenameFormat, __config__.tagsSeparator, __config__.tagsLimit, artist, targetDir)
                result = downloadImage(artist.artistAvatar, avatarFilename, listPage.geturl(), __config__.overwrite, __config__.retry, __config__.backupOldFile)
                avatarDownloaded = True

            __dbManager__.updateMemberName(member_id, artist.artistName)

            if not artist.haveImages:
                PixivHelper.printAndLog('info', "No image found for: " + str(member_id))
                flag = False
                continue

            result = PixivConstant.PIXIVUTIL_NOT_OK
            for image_id in artist.imageList:
                print '#'+ str(noOfImages)
                if mode == PixivConstant.PIXIVUTIL_MODE_UPDATE_ONLY:
                    r = __dbManager__.selectImageByMemberIdAndImageId(member_id, image_id)
                    if r != None and not(__config__.alwaysCheckFileSize):
                        print 'Already downloaded:', image_id
                        updatedLimitCount = updatedLimitCount + 1
                        if updatedLimitCount > __config__.checkUpdatedLimit and __config__.checkUpdatedLimit != 0 :
                            print 'Skipping member:', member_id
                            __dbManager__.updateLastDownloadedImage(member_id, image_id)

                            del listPage
                            __br__.clear_history()
                            return
                        gc.collect()
                        continue

                retryCount = 0
                while True :
                    try:
                        titlePrefix = "MemberId: {0} Page: {1} Image {2}+{3} of {4}".format(member_id, page, noOfImages, updatedLimitCount, ((page - 1) * 20 ) + len(artist.imageList))
                        result = processImage(mode, artist, image_id, userDir, bookmark, titlePrefix=titlePrefix) #Yavos added dir-argument to pass
                        __dbManager__.insertImage(member_id, image_id)
                        break
                    except KeyboardInterrupt:
                        result = PixivConstant.PIXIVUTIL_KEYBOARD_INTERRUPT
                        break
                    except:
                        if retryCount > __config__.retry:
                            PixivHelper.printAndLog('error', "Giving up image_id: "+str(image_id))
                            return
                        retryCount = retryCount + 1
                        print "Stuff happened, trying again after 2 second (", retryCount,")"
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        traceback.print_exception(exc_type, exc_value, exc_traceback)
                        __log__.exception('Error at processMember(): ' + str(sys.exc_info()) + ' Member Id: ' + str(member_id))
                        time.sleep(2)

                noOfImages = noOfImages + 1

                if result == PixivConstant.PIXIVUTIL_KEYBOARD_INTERRUPT:
                    choice = raw_input("Keyboard Interrupt detected, continue to next image (Y/N)")
                    if choice.upper() == 'N':
                        PixivHelper.printAndLog("info", "Member: " + str(member_id) + ", processing aborted")
                        flag = False
                        break
                    else :
                        continue

                ## return code from process image
                if result == PixivConstant.PIXIVUTIL_SKIP_OLDER:
                    PixivHelper.printAndLog("info", "Reached older images, skippin to next member.")
                    flag = False
                    break

            if artist.isLastPage:
                print "Last Page"
                flag = False

            page = page + 1

            ## page limit checking
            if endPage > 0 and page > endPage:
                print "Page limit reached (from endPage limit =" + str(endPage) + ")"
                flag = False
            else:
                if npisvalid == True: #Yavos: overwriting config-data
                    if page > np and np > 0:
                        print "Page limit reached (from command line =" + str(np) + ")"
                        flag = False
                elif page > __config__.numberOfPage and __config__.numberOfPage > 0 :
                    print "Page limit reached (from config =" + str(__config__.numberOfPage) + ")"
                    flag = False

            del artist
            del listPage
            __br__.clear_history()
            gc.collect()

        __dbManager__.updateLastDownloadedImage(member_id, image_id)
        print 'Done.\n'
        __log__.info('Member_id: ' + str(member_id) + ' complete, last image_id: ' + str(image_id))
    except KeyboardInterrupt:
        raise
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        PixivHelper.printAndLog('error', 'Error at processMember(): ' + str(sys.exc_info()))
        __log__.exception('Error at processMember(): '+ str(member_id))
        try:
            if listPage != None :
                dumpFilename = 'Error page for member ' + str(member_id) + '.html'
                PixivHelper.dumpHtml(dumpFilename, listPage.get_data())
                PixivHelper.printAndLog('error', "Dumping html to: " + dumpFilename)
        except:
            PixivHelper.printAndLog('error', 'Cannot dump page for member_id:'+str(member_id))
        raise

def processImage(mode, artist=None, image_id=None, userDir='', bookmark=False, searchTags='', titlePrefix=None):
    #Yavos added dir-argument which will be initialized as '' when not given
    parseBigImage = None
    mediumPage = None
    viewPage = None
    image = None
    try:
        filename = 'N/A'
        print 'Processing Image Id:', image_id
        ## check if already downloaded. images won't be downloaded twice - needed in processImage to catch any download
        r = __dbManager__.selectImageByImageId(image_id)
        if r != None and not __config__.alwaysCheckFileSize:
            if mode == PixivConstant.PIXIVUTIL_MODE_UPDATE_ONLY:
                print 'Already downloaded:', image_id
                gc.collect()
                return

        retryCount = 0
        while 1:
            try :
                mediumPage = __br__.open('http://www.pixiv.net/member_illust.php?mode=medium&illust_id='+str(image_id))
                parseMediumPage = BeautifulSoup(mediumPage.read())
                image = PixivImage(iid=image_id, page=parseMediumPage, parent=artist, fromBookmark=bookmark)
                if titlePrefix != None:
                  setTitle(titlePrefix + " ImageId: {0}".format(image.imageId))
                else:
                  setTitle('MemberId: ' + str(image.artist.artistId) + ' ImageId: ' + str(image.imageId))
                parseMediumPage.decompose()
                del parseMediumPage
                break
            except PixivException as ex:
                if ex.errorCode == PixivException.UNKNOWN_IMAGE_ERROR:
                    PixivHelper.safePrint(ex.message)
                    raw_input('New Error Message, please inform the developer. Press enter to continue.')
                elif ex.errorCode == PixivException.SERVER_ERROR:
                    print ex
                    repeat = range(1,__config__.retryWait)
                    for t in repeat:
                        print t,
                        time.sleep(1)
                    print ''
                    ++retryCount
                    if retryCount > __config__.retry:
                        PixivHelper.printAndLog('error', 'Giving up image_id (medium): ' + str(image_id))
                        if mediumPage != None:
                            dumpFilename = 'Error medium page for image ' + str(image_id) + '.html'
                            PixivHelper.dumpHtml(dumpFilename , mediumPage.get_data())
                            PixivHelper.printAndLog('error', 'Dumping html to: ' + dumpFilename);
                        return
                else:
                    PixivHelper.printAndLog('info', 'Image ID (' + str(image_id) +'): ' + str(ex))
                return
            except urllib2.URLError as ue:
                print ue
                repeat = range(1,__config__.retryWait)
                for t in repeat:
                    print t,
                    time.sleep(1)
                print ''
                ++retryCount
                if retryCount > __config__.retry:
                    PixivHelper.printAndLog('error', 'Giving up image_id (medium): ' + str(image_id))
                    if mediumPage != None:
                        dumpFilename = 'Error medium page for image ' + str(image_id) + '.html'
                        PixivHelper.dumpHtml(dumpFilename , mediumPage.get_data())
                        PixivHelper.printAndLog('error', 'Dumping html to: ' + dumpFilename);
                    return

        downloadImageFlag = True

        if __config__.dateDiff > 0:
            if image.worksDateDateTime != datetime.datetime.fromordinal(1):
                if image.worksDateDateTime < datetime.datetime.today() - datetime.timedelta(__config__.dateDiff):
                    PixivHelper.printAndLog('info', 'Skipping image_id: ' + str(image_id) + ' because contains older than: ' + str(__config__.dateDiff) + ' day(s).');
                    downloadImageFlag = False
                    result = PixivConstant.PIXIVUTIL_SKIP_OLDER

        if __config__.useBlacklistTags:
            for item in __blacklistTags:
                if item in image.imageTags:
                    PixivHelper.printAndLog('info', 'Skipping image_id: ' + str(image_id) + ' because contains blacklisted tags: ' + item);
                    downloadImageFlag = False
                    result = PixivConstant.PIXIVUTIL_SKIP_BLACKLIST
                    break

        if downloadImageFlag:

            PixivHelper.safePrint("Title: " + image.imageTitle)
            PixivHelper.safePrint("Tags : " + ', '.join(image.imageTags))
            PixivHelper.safePrint("Date : " + str(image.worksDateDateTime))
            print "Mode :", image.imageMode

            if __config__.useSuppressTags:
                for item in __suppressTags:
                    if item in image.imageTags:
                        image.imageTags.remove(item)

            errorCount = 0
            while True:
                try :
                    bigUrl = 'http://www.pixiv.net/member_illust.php?mode='+image.imageMode+'&illust_id='+str(image_id)
                    viewPage = __br__.follow_link(url_regex='mode='+image.imageMode+'&illust_id='+str(image_id))
                    parseBigImage = BeautifulSoup(viewPage.read())
                    if parseBigImage != None:
                        image.ParseImages(page=parseBigImage)
                        parseBigImage.decompose()
                        del parseBigImage
                    break
                except PixivException as ex:
                    PixivHelper.printAndLog('info', 'Image ID (' + str(image_id) +'): ' + str(ex))
                    return
                except urllib2.URLError as ue:
                    if errorCount > __config__.retry:
                        PixivHelper.printAndLog('error', 'Giving up image_id: '+str(image_id))
                        return
                    errorCount = errorCount + 1
                    print ue
                    repeat = range(1,__config__.retryWait)
                    for t in repeat:
                        print t,
                        time.sleep(1)
                    print ''
            if image.imageMode == 'manga':
                print "Page Count :", image.imageCount

            result = PixivConstant.PIXIVUTIL_OK
            skipOne = False
            for img in image.imageUrls:
                if skipOne:
                    skipOne = False
                    continue
                print 'Image URL :', img
                url = os.path.basename(img)
                splittedUrl = url.split('.')
                if splittedUrl[0].startswith(str(image_id)):
                    #Yavos: filename will be added here if given in list
                    filenameFormat = __config__.filenameFormat
                    if image.imageMode == 'manga':
                        filenameFormat = __config__.filenameMangaFormat

                    if userDir == '': #Yavos: use config-options
                        targetDir = __config__.rootDirectory
                    else: #Yavos: use filename from list
                        targetDir = userDir

                    filename = PixivHelper.makeFilename(filenameFormat, image, tagsSeparator=__config__.tagsSeparator, tagsLimit=__config__.tagsLimit, fileUrl=url, bookmark=bookmark, searchTags=searchTags)
                    filename = PixivHelper.sanitizeFilename(filename, targetDir)

                    if image.imageMode == 'manga' and __config__.createMangaDir :
                        mangaPage = __re_manga_page.findall(filename)
                        if len(mangaPage) > 0:
                            splittedFilename = filename.split(mangaPage[0][0],1)
                            splittedMangaPage = mangaPage[0][0].split("_p",1)
                            filename = splittedFilename[0] + splittedMangaPage[0] + os.sep + "_p" + splittedMangaPage[1] + splittedFilename[1]

                    PixivHelper.safePrint('Filename  : ' + filename)
                    result = PixivConstant.PIXIVUTIL_NOT_OK
                    try:
                        overwrite = False
                        if mode == PixivConstant.PIXIVUTIL_MODE_OVERWRITE:
                            overwrite = True
                        result = downloadImage(img, filename, viewPage.geturl(), overwrite, __config__.retry, __config__.backupOldFile)

                        if result == PixivConstant.PIXIVUTIL_NOT_OK and image.imageMode == 'manga' and img.find('_big') > -1:
                            print 'No big manga image available, try the small one'
                        elif result == PixivConstant.PIXIVUTIL_OK and image.imageMode == 'manga' and img.find('_big') > -1:
                            skipOne = True
                        elif result == PixivConstant.PIXIVUTIL_NOT_OK:
                            PixivHelper.printAndLog('error', 'Image url not found: '+str(image.imageId))
                    except urllib2.URLError as ue:
                        PixivHelper.printAndLog('error', 'Giving up url: '+str(img))
                        __log__.exception('Error when downloadImage(): ' +str(img))
                    print ''

            if __config__.writeImageInfo:
                image.WriteInfo(filename + ".txt")

        ## Only save to db if all images is downloaded completely
        if result == PixivConstant.PIXIVUTIL_OK :
            try:
                __dbManager__.insertImage(image.artist.artistId, image.imageId)
            except:
                pass
            __dbManager__.updateImage(image.imageId, image.imageTitle, filename)

        if mediumPage != None:
            del mediumPage
        if viewPage != None:
            del viewPage
        if image != None:
            del image
        gc.collect()
        ##clearall()
        print '\n'
        return result
    except KeyboardInterrupt:
        raise
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        PixivHelper.printAndLog('error', 'Error at processImage(): ' + str(sys.exc_info()))
        __log__.exception('Error at processImage(): ' +str(image_id))
        try:
            if viewPage != None:
                dumpFilename = 'Error Big Page for image ' + str(image_id) + '.html'
                PixivHelper.dumpHtml(dumpFilename , viewPage.get_data())
                PixivHelper.printAndLog('error', 'Dumping html to: ' + dumpFilename);
        except:
            PixivHelper.printAndLog('error', 'Cannot dump big page for image_id: '+str(image_id))
        try:
            if mediumPage != None:
                dumpFilename = 'Error Medium Page for image ' + str(image_id) + '.html'
                PixivHelper.dumpHtml(dumpFilename , mediumPage.get_data())
                PixivHelper.printAndLog('error', 'Dumping html to: ' + dumpFilename);
        except:
            PixivHelper.printAndLog('error', 'Cannot medium dump page for image_id: '+str(image_id))
        raise

def processTags(mode, tags, page=1, endPage=0, wildCard=True, titleCaption=False, startDate=None, endDate=None, useTagsAsDir=False, member_id=None, bookmarkCount=None):
    try:
        __config__.loadConfig() ## Reset the config for root directory

        try:
            if tags.startswith("%") :
                searchTags = PixivHelper.toUnicode(urllib.unquote_plus(tags))
            else:
                searchTags = PixivHelper.toUnicode(tags)
        except UnicodeDecodeError as ex:
            ## From command prompt
            searchTags = tags.decode(sys.stdout.encoding).encode("utf8")
            searchTags = PixivHelper.toUnicode(searchTags)

        if useTagsAsDir:
            print "Save to each directory using query tags."
            __config__.rootDirectory += os.sep + PixivHelper.sanitizeFilename(searchTags)

        if not tags.startswith("%") :
            try:
                ## Encode the tags
                tags = tags.encode('utf-8')
                tags = urllib.quote_plus(tags)
            except UnicodeDecodeError as ex:
                try:
                    ## from command prompt
                    tags = urllib.quote_plus(tags.decode(sys.stdout.encoding).encode("utf8"))
                except UnicodeDecodeError as ex:
                    PixivHelper.printAndLog('error', 'Cannot decode the tags, you can use URL Encoder (http://meyerweb.com/eric/tools/dencoder/) and paste the encoded tag.')
                    __log__.exception('decodeTags()')
        i = page
        images = 1
        skippedCount = 0

        dateParam = ""
        if startDate != None:
            dateParam = dateParam + "&scd=" + startDate
        if endDate != None:
            dateParam = dateParam + "&ecd=" + endDate

        PixivHelper.printAndLog('info', 'Searching for: ('+ searchTags + ") " + tags + dateParam)
        flag = True
        while flag:
            if not member_id == None:
                url = 'http://www.pixiv.net/member_illust.php?id=' + str(member_id) + '&tag=' + tags + '&p='+str(i)
            else :
                if titleCaption:
                    url = 'http://www.pixiv.net/search.php?s_mode=s_tc&p='+str(i)+'&word='+tags + dateParam
                else:
                    if wildCard:
                        url = 'http://www.pixiv.net/search.php?s_mode=s_tag&p='+str(i)+'&word='+tags + dateParam
                        print "Using Wildcard (search.php)"
                    else:
                        url = 'http://www.pixiv.net/search.php?s_mode=s_tag_full&word='+tags+'&p='+str(i) + dateParam

            if __config__.r18mode:
                url = url + '&r18=1'

            PixivHelper.printAndLog('info', 'Looping... for '+ url)
            searchPage = __br__.open(url)

            parseSearchPage = BeautifulSoup(searchPage.read())
            t = PixivTags()
            l = list()
            if not member_id == None:
                l = t.parseMemberTags(parseSearchPage)
            else :
                l = t.parseTags(parseSearchPage)

            if len(l) == 0 :
                print 'No more images'
                flag = False
            else:
                for item in t.itemList:
                    print 'Image #' + str(images)
                    print 'Image Id:', str(item.imageId)
                    print 'Bookmark Count:', str(item.bookmarkCount)
                    if bookmarkCount != None and bookmarkCount > item.bookmarkCount:
                        PixivHelper.printAndLog('info', 'Skipping imageId='+str(item.imageId)+' because less than bookmark count limit ('+ str(bookmarkCount) + ' > ' + str(item.bookmarkCount) + ')')
                        skippedCount = skippedCount + 1
                        continue
                    result = 0
                    while True:
                        try:
                            totalImage = ((i - 1) * 20) + len(t.itemList)
                            titlePrefix = "Tags:{0} Page:{1} Image {2}+{3} of {4}".format(tags, i, images, skippedCount, totalImage)
                            if not member_id == None:
                              titlePrefix = "MemberId: {0} Tags:{1} Page:{2} Image {3}+{4} of {5}".format(member_id, tags, i, images, skippedCount, totalImage)
                            processImage(mode, None, item.imageId, searchTags=searchTags, titlePrefix=titlePrefix)
                            break
                        except KeyboardInterrupt:
                            result = PixivConstant.PIXIVUTIL_KEYBOARD_INTERRUPT
                            break
                        except httplib.BadStatusLine:
                            print "Stuff happened, trying again after 2 second..."
                            time.sleep(2)

                    images = images + 1

                    if result == PixivConstant.PIXIVUTIL_KEYBOARD_INTERRUPT:
                        choice = raw_input("Keyboard Interrupt detected, continue to next image (Y/N)")
                        if choice.upper() == 'N':
                            PixivHelper.printAndLog("info", "Tags: " + tags + ", processing aborted")
                            flag = False
                            break
                        else :
                            continue

            __br__.clear_history()

            i = i + 1

            parseSearchPage.decompose()
            del parseSearchPage
            del searchPage

            if endPage != 0 and endPage < i:
                print 'End Page reached.'
                flag = False
            if t.isLastPage:
                print 'Last page'
                flag = False
        print 'done'
    except KeyboardInterrupt:
        raise
    except:
        print 'Error at processTags():',sys.exc_info()
        __log__.exception('Error at processTags(): ' + str(sys.exc_info()))
        raise

def processTagsList(mode, filename, page=1, endPage=0):
    try:
        print "Reading:",filename
        l = PixivTags.parseTagsList(filename)
        for tag in l:
            processTags(mode, tag, page=page, endPage=endPage, useTagsAsDir=__config__.useTagsAsDir)
    except KeyboardInterrupt:
        raise
    except:
        print 'Error at processTagsList():',sys.exc_info()
        __log__.exception('Error at processTagsList(): ' + str(sys.exc_info()))
        raise

def processImageBookmark(mode, hide='n', startPage = 1, endPage = 0):
    try:
        print "Importing image bookmarks..."
        #totalList = list()
        i = startPage
        imageCount = 1
        while True:
            if endPage != 0 and i > endPage:
                print "Page Limit reached: " + str(endPage)
                break

            print "Importing user's bookmarked image from page", str(i),
            url = 'http://www.pixiv.net/bookmark.php?p='+str(i)
            if hide == 'y':
                url = url + "&rest=hide"
            page = __br__.open(url)
            parsePage = BeautifulSoup(page.read())
            l = PixivBookmark.parseImageBookmark(parsePage)
            if len(l) == 0:
                print "No more images."
                break
            else :
                print " found " + str(len(l)) + " images."

            for item in l:
                print "Image #" + str(imageCount)
                processImage(mode, artist=None, image_id=item)
                imageCount = imageCount + 1

            i = i + 1

            parsePage.decompose()
            del parsePage

            if npisvalid == True: #Yavos: overwrite config-data
                if i > np and np != 0:
                    break
            elif i > __config__.numberOfPage and __config__.numberOfPage != 0 :
                break

        print "Done.\n"
    except KeyboardInterrupt:
        raise
    except :
        print 'Error at processImageBookmark():',sys.exc_info()
        __log__.exception('Error at processImageBookmark(): ' + str(sys.exc_info()))
        raise

def getBookmarks(hide, startPage = 1, endPage = 0):
    '''Get user/artists bookmark'''
    totalList = list()
    i = startPage
    while True:
        if endPage != 0 and i > endPage:
            print 'Limit reached'
            break
        print 'Exporting page', str(i),
        url = 'http://www.pixiv.net/bookmark.php?type=user&p='+str(i)
        if hide:
            url = url + "&rest=hide"
        page = __br__.open(url)
        parsePage = BeautifulSoup(page.read())
        l = PixivBookmark.parseBookmark(parsePage)
        if len(l) == 0:
            print 'No more data'
            break
        totalList.extend(l)
        i = i + 1
        print str(len(l)), 'items'
    return totalList

def processBookmark(mode, hide='n', startPage = 1, endPage = 0):
    try:
        totalList = list()
        if hide != 'o':
            print "Importing Bookmarks..."
            totalList.extend(getBookmarks(False, startPage, endPage))
        if hide != 'n':
            print "Importing Private Bookmarks..."
            totalList.extend(getBookmarks(True, startPage, endPage))
        print "Result: ", str(len(totalList)), "items."
        for item in totalList:
            processMember(mode, item.memberId, item.path)
    except KeyboardInterrupt:
        raise
    except :
        print 'Error at processBookmark():',sys.exc_info()
        __log__.exception('Error at processBookmark(): ' + str(sys.exc_info()))
        raise

def exportBookmark(filename, hide='n', startPage = 1, endPage = 0):
    try:
        totalList = list()
        if hide != 'o':
            print "Importing Bookmarks..."
            totalList.extend(getBookmarks(False, startPage, endPage))
        if hide != 'n':
            print "Importing Private Bookmarks..."
            totalList.extend(getBookmarks(True, startPage, endPage))
        print "Result: ", str(len(totalList)), "items."
        PixivBookmark.exportList(totalList, filename)
    except KeyboardInterrupt:
        raise
    except :
        print 'Error at exportBookmark():',sys.exc_info()
        __log__.exception('Error at exportBookmark(): ' + str(sys.exc_info()))
        raise

def processNewIllustFromBookmark(mode, pageNum=1, endPageNum=0):
    try:
        print "Processing New Illust from bookmark"
        i = pageNum
        imageCount = 1
        flag = True
        while flag:
            print "Page #"+str(i)
            url = 'http://www.pixiv.net/bookmark_new_illust.php?p='+str(i)
            page = __br__.open(url)
            parsedPage = BeautifulSoup(page.read())
            pb = PixivNewIllustBookmark(parsedPage)
            if not pb.haveImages:
                print "No images!"
                break

            for image_id in pb.imageList:
                print "Image #"+str(imageCount)
                result = processImage(mode, artist=None, image_id=int(image_id))
                imageCount = imageCount + 1

                if result == PixivConstant.PIXIVUTIL_SKIP_OLDER:
                    flag = False
                    break
            i = i + 1

            parsedPage.decompose()
            del parsedPage

            if ( endPageNum != 0 and i > endPageNum ) or i >= 100 or pb.isLastPage:
                print "Limit or last page reached."
                flag = False

        print "Done."
    except KeyboardInterrupt:
        raise
    except:
        print 'Error at processNewIllustFromBookmark():',sys.exc_info()
        __log__.exception('Error at processNewIllustFromBookmark(): ' + str(sys.exc_info()))
        raise

def processFromGroup(mode, groupId, limit = 0, processExternal=True):
   try:
      print "Download by Group Id"
      if limit != 0:
         print "Limit: {0}".format(limit)
      if processExternal:
         print "Include External Image: {0}".format(processExternal)

      maxId = 0
      imageCount = 0
      flag = True
      while(flag):
         url = "http://www.pixiv.net/group/images.php?format=json&max_id={0}&id={1}".format(maxId, groupId)
         print "Getting images from: {0}".format(url)
         jsonResponse = __br__.open(url)
         groupData = PixivGroup(jsonResponse)
         maxId = groupData.maxId
         if groupData.imageList!= None and len(groupData.imageList) > 0:
            for image in groupData.imageList:
               if imageCount > limit and limit != 0:
                  flag = False
                  break
               print "Image #{0}".format(imageCount)
               print "ImageId: {0}".format(image)
               processImage(mode, image_id=image)
               imageCount = imageCount + 1

         if processExternal and groupData.externalImageList!= None and len(groupData.externalImageList) > 0:
            for image_data in groupData.externalImageList:
               if imageCount > limit and limit != 0:
                  flag = False
                  break
               print "Image #{0}".format(imageCount)
               print "Member Id    : {0}".format(image_data.artist.artistId)
               PixivHelper.safePrint("Member Name  : "+ image_data.artist.artistName)
               print "Member Token : {0}".format(image_data.artist.artistToken)
               print "Image Url    : {0}".format(image_data.imageUrls[0])

               filename = PixivHelper.makeFilename(__config__.filenameFormat, imageInfo=image_data, tagsSeparator=__config__.tagsSeparator, tagsLimit=__config__.tagsLimit, fileUrl=image_data.imageUrls[0])
               filename = PixivHelper.sanitizeFilename(filename, __config__.rootDirectory)
               PixivHelper.safePrint("Filename  : "+ filename)
               downloadImage(image_data.imageUrls[0], filename, url, __config__.overwrite, __config__.retry, __config__.backupOldFile)
               imageCount = imageCount + 1

         if (groupData.imageList == None or len(groupData.imageList) == 0) and (groupData.externalImageList == None or len(groupData.externalImageList) == 0):
            flag = False
         print ""

   except:
      print 'Error at processFromGroup():',sys.exc_info()
      __log__.exception('Error at processFromGroup(): ' + str(sys.exc_info()))
      raise

def header():
    print 'PixivDownloader2 version', PixivConstant.PIXIVUTIL_VERSION
    print PixivConstant.PIXIVUTIL_LINK

def getStartAndEndNumber(startOnly=False):
    pageNum = raw_input('Start Page (default=1): ') or 1
    try:
        pageNum = int(pageNum)
    except:
        print "Invalid page number:", pageNum
        raise

    endPageNum = 0
    if npisvalid:
        endPageNum = np
    else:
        endPageNum = __config__.numberOfPage

    if not startOnly:
        endPageNum = raw_input('End Page (default='+ str(endPageNum) +', 0 for no limit): ') or endPageNum
        try:
            endPageNum = int(endPageNum)
            if pageNum > endPageNum and endPageNum != 0:
                print "pageNum is bigger than endPageNum, assuming as page count."
                endPageNum = pageNum + endPageNum
        except:
            print "Invalid end page number:", endPageNum
            raise

    return (pageNum, endPageNum)

def getStartAndEndNumberFromArgs(args, offset=0, startOnly=False):
    pageNum = 1
    if len(args) > 0+offset:
        try:
            pageNum = int(args[0+offset])
            print "Start Page =", str(pageNum)
        except:
            print "Invalid page number:", args[0+offset]
            raise

    endPageNum = 0
    if npisvalid:
        endPageNum = np
    else:
        endPageNum = __config__.numberOfPage

    if not startOnly:
        if len(args) > 1+offset:
            try:
                endPageNum = int(args[1+offset])
                if pageNum > endPageNum and endPageNum != 0:
                    print "pageNum is bigger than endPageNum, assuming as page count."
                    endPageNum = pageNum + endPageNum
                print "End Page =", str(endPageNum)
            except:
                print "Invalid end page number:", args[1+offset]
                raise
    return (pageNum, endPageNum)

def checkDateTime(inputDate):
    split = inputDate.split("-")
    return datetime.date(int(split[0]),int(split[1]),int(split[2])).isoformat()

def getStartAndEndDate():
    while(True):
        try:
            startDate = raw_input('Start Date [YYYY-MM-DD]: ') or None
            if startDate != None:
                startDate = checkDateTime(startDate)
            break
        except Exception as e:
            print str(e)

    while(True):
        try:
            endDate = raw_input('End Date [YYYY-MM-DD]: ') or None
            if endDate != None:
                endDate = checkDateTime(endDate)
            break
        except Exception as e:
                print str(e)

    return (startDate, endDate)

def menu():
    setTitle()
    header()
    print '1. Download by member_id'
    print '2. Download by image_id'
    print '3. Download by tags'
    print '4. Download from list'
    print '5. Download from online user bookmark'
    print '6. Download from online image bookmark'
    print '7. Download from tags list'
    print '8. Download new illust from bookmark'
    print '9. Download by Title/Caption'
    print '10. Download by Tag and Member Id'
    print '11. Download Member Bookmark'
    print '12. Download by Group Id'
    print '------------------------'
    print 'd. Manage database'
    print 'e. Export online bookmark'
    print 'r. Reload config.ini'
    print 'p. Print config.ini'
    print 'x. Exit'

    return raw_input('Input: ').strip()

def menuDownloadByMemberId(mode, opisvalid, args):
    __log__.info('Member id mode.')
    page = 1
    endPage = 0
    if opisvalid and len(args) > 0:
        for member_id in args:
            try:
                testID = int(member_id)
            except:
                print "ID", member_id, "is not valid"
                continue
            processMember(mode, int(member_id))
    else:
        member_id = raw_input('Member id: ')
        (page, endPage) = getStartAndEndNumber()
        processMember(mode, member_id.strip(), page=page, endPage=endPage)

def menuDownloadByMemberBookmark(mode, opisvalid, args):
    __log__.info('Member Bookmark mode.')
    page = 1
    endPage = 0
    if opisvalid and len(args) > 0:
        for member_id in args:
            try:
                testID = int(member_id)
            except:
                print "ID", member_id, "is not valid"
                continue
            processMember(mode, int(member_id))
    else:
        member_id = raw_input('Member id: ')
        (page, endPage) = getStartAndEndNumber()
        processMember(mode, member_id.strip(), page=page, endPage=endPage, bookmark=True)

def menuDownloadByImageId(mode, opisvalid, args):
    __log__.info('Image id mode.')
    if opisvalid and len(args) > 0:
        for image_id in args:
            try:
                testID = int(image_id)
            except:
                print "ID", image_id, "is not valid"
                continue
            processImage(mode, None, int(image_id))
    else:
        image_id = raw_input('Image id: ')
        processImage(mode, None, int(image_id))

def menuDownloadByTags(mode, opisvalid, args):
    __log__.info('tags mode.')
    page = 1
    endPage = 0
    startDate = None
    endDate = None
    bookmarkCount = None
    if opisvalid and len(args) > 0:
        wildcard = args[0]
        if wildcard.lower() == 'y':
            wildcard = True
        else:
            wildcard = False
        tags = " ".join(args[1:])
    else:
        tags = PixivHelper.uni_input('Tags: ')
        bookmarkCount = raw_input('Bookmark Count: ') or None
        wildcard = raw_input('Use Wildcard[y/n]: ') or 'n'
        if wildcard.lower() == 'y':
            wildcard = True
        else:
            wildcard = False
        (page, endPage) = getStartAndEndNumber()
        (startDate, endDate) = getStartAndEndDate()
    if bookmarkCount != None:
        bookmarkCount = int(bookmarkCount)
    processTags(mode, tags.strip(), page, endPage, wildcard, startDate=startDate, endDate=endDate, useTagsAsDir=__config__.useTagsAsDir,bookmarkCount=bookmarkCount)

def menuDownloadByTitleCaption(mode, opisvalid, args):
    __log__.info('Title/Caption mode.')
    page = 1
    endPage = 0
    startDate = None
    endDate = None
    if opisvalid and len(args) > 0:
        tags = " ".join(args)
    else:
        tags = PixivHelper.uni_input('Title/Caption: ')
        (page, endPage) = getStartAndEndNumber()
        (startDate, endDate) = getStartAndEndDate()

    processTags(mode, tags.strip(), page, endPage, wildCard=False, titleCaption=True, startDate=startDate, endDate=endDate, useTagsAsDir=__config__.useTagsAsDir)

def menuDownloadByTagAndMemberId(mode, opisvalid, args):
    __log__.info('Tag and MemberId mode.')
    member_id = 0
    tags = None

    if opisvalid and len(args) >= 2:
        member_id = int(args[0])
        tags = " ".join(args[1:])
        PixivHelper.safePrint("Looking tags: " + tags + " from memberId: " + str(member_id))
    else:
        member_id = raw_input('Member Id: ')
        tags      = PixivHelper.uni_input('Tag      : ')

    processTags(mode, tags.strip(), member_id=int(member_id), useTagsAsDir=__config__.useTagsAsDir)


def menuDownloadFromList(mode, opisvalid, args):
    __log__.info('Batch mode.')
    processList(mode)

def menuDownloadFromOnlineUserBookmark(mode, opisvalid, args):
    __log__.info('User Bookmark mode.')
    startPage = 1
    endPage = 0
    hide = 'n'
    if opisvalid :
        if len(args) > 0:
            arg = args[0].lower()
            if arg == 'y' or arg =='n' or arg == 'o':
                hide = arg
            else:
                print "Invalid args: ", args
                return
            (startPage, endPage) = getStartAndEndNumberFromArgs(args, offset=1)
    else :
        arg = raw_input("Include Private bookmarks [y/n/o]: ") or 'n'
        arg = arg.lower()
        if arg == 'y' or arg =='n' or arg == 'o':
            hide = arg
        else:
            print "Invalid args: ", arg
            return
        (startPage, endPage) = getStartAndEndNumber()
    processBookmark(mode, hide, startPage, endPage)

def menuDownloadFromOnlineImageBookmark(mode, opisvalid, args):
    __log__.info("User's Image Bookmark mode.")
    startPage = 1
    endPage = 0
    if opisvalid and len(args) > 0 :
        arg = args[0].lower()
        if arg == 'y' or arg =='n':
            hide = arg
        else:
            print "Invalid args: ", args
            return
        (startPage, endPage) = getStartAndEndNumberFromArgs(args, offset=1)
    else:
        hide = False
        arg = raw_input("Only Private bookmarks [y/n]: ") or 'n'
        arg = arg.lower()
        if arg == 'y' or arg =='n':
            hide = arg
        else:
            print "Invalid args: ", arg
            return
        (startPage, endPage) = getStartAndEndNumber()

    processImageBookmark(mode, hide, startPage, endPage)

def menuDownloadFromTagsList(mode, opisvalid, args):
    __log__.info('Taglist mode.')
    page = 1
    endPage = 0
    if opisvalid and len(args) > 0 :
        filename = args[0]
        (page, endPage) = getStartAndEndNumberFromArgs(args, offset=1)
    else:
        filename = raw_input("Tags list filename [tags.txt]: ") or './tags.txt'
        (page, endPage) = getStartAndEndNumber()

    processTagsList(mode, filename, page, endPage)

def menuDownloadNewIllustFromBookmark(mode, opisvalid, args):
    __log__.info('New Illust from Bookmark mode.')

    if opisvalid:
        (pageNum, endPageNum) = getStartAndEndNumberFromArgs(args, offset=0)
    else:
        (pageNum, endPageNum) = getStartAndEndNumber()

    processNewIllustFromBookmark(mode, pageNum, endPageNum)

def menuDownloadByGroupId(mode, opisvalid, args):
    __log__.info('Group mode.')
    processExternal = False
    limit = 0

    if opisvalid and len(args) > 0 :
        groupId = args[0]
        limit = int(args[1])
        processExternal = bool(args[2])
    else:
        groupId = raw_input("Group Id: ")
        limit = int(raw_input("Limit: "))
        arg = raw_input("Process External Image [y/n]: ") or 'n'
        arg = arg.lower()
        if arg == 'y':
            processExternal = True

    processFromGroup(mode, groupId, limit, processExternal)

def menuExportOnlineBookmark(mode, opisvalid, args):
    __log__.info('Export Bookmark mode.')
    filename = raw_input("Filename: ")
    arg = raw_input("Include Private bookmarks [y/n/o]: ") or 'n'
    arg = arg.lower()
    if arg == 'y' or arg =='n' or arg == 'o':
        hide = arg
    else:
        print "Invalid args: ", arg
    exportBookmark(filename, hide)

def menuReloadConfigIni():
    __log__.info('Manual Reload Config.')
    __config__.loadConfig()

def menuPrintConfigIni():
    __log__.info('Manual Reload Config.')
    __config__.printConfig()

def setTitle(title=''):
    setTitle = 'PixivDownloader ' + str(PixivConstant.PIXIVUTIL_VERSION) + ' ' + title
    PixivHelper.setConsoleTitle(setTitle)

### Main thread ###
def main():
    setTitle()
    header()

    ## Option Parser
    global npisvalid
    global opisvalid
    global np
    global iv
    global op
    global args
    global __br__

    parser = OptionParser()
    parser.add_option('-s', '--startaction', dest='startaction',
                      help='Action you want to load your program with:              ' +
                           '1 - Download by member_id                               ' +
                           '2 - Download by image_id                                ' +
                           '3 - Download by tags                                    ' +
                           '4 - Download from list                                  ' +
                           '5 - Download from user bookmark                          ' +
                           '6 - Download from user\'s image bookmark                 ' +
                           '7 - Download from tags list                              ' +
                           '8 - Download new illust from bookmark                    ' +
                           '9 - Download by Title/Caption                            ' +
                           '10 - Download by Tag and Member Id                       ' +
                           '11 - Download images from Member Bookmark                ' +
                           'e - Export online bookmark                               ' +
                           'd - Manage database' )
    parser.add_option('-x', '--exitwhendone', dest='exitwhendone',
                      help='Exit programm when done. (only useful when not using DB-Manager)', action='store_true', default=False)
    parser.add_option('-i', '--irfanview', dest='iv',
                      help='start IrfanView after downloading images using downloaded_on_%date%.txt', action='store_true', default=False)
    parser.add_option('-n', '--numberofpages', dest='numberofpages',
                      help='temporarily overwrites numberOfPage set in config.ini')

    (options, args) = parser.parse_args()

    op = options.startaction
    if op in ('1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', 'd', 'e'):
        opisvalid = True
    elif op == None:
        opisvalid = False
    else:
        opisvalid = False
        parser.error('%s is not valid operation' % op) #Yavos: use print option instead when program should be running even with this error

    ewd = options.exitwhendone
    try:
        if options.numberofpages != None:
            np = int(options.numberofpages)
            npisvalid = True
        else:
            npisvalid = False
    except:
        npisvalid = False
        parser.error('Value %s used for numberOfPage is not an integer.' % options.numberofpages) #Yavos: use print option instead when program should be running even with this error
    ### end new lines by Yavos ###
    __log__.info('###############################################################')
    __log__.info('Starting...')
    try:
        __config__.loadConfig()
        PixivHelper.setConfig(__config__)
    except:
        print 'Failed to read configuration.'
        __log__.exception('Failed to read configuration.')

    PixivHelper.setLogLevel(__config__.logLevel)
    if __br__ == None:
        __br__ = PixivBrowserFactory.getBrowser(config=__config__)
    PixivBrowserFactory.configureBrowser(__br__, __config__)

    selection = None
    global dfilename

    #Yavos: adding File for downloadlist
    now = datetime.date.today()
    dfilename = __config__.downloadListDirectory + os.sep + 'Downloaded_on_' + now.strftime('%Y-%m-%d') + '.txt'
    if not re.match(r'[a-zA-Z]:', dfilename):
        dfilename = PixivHelper.toUnicode(sys.path[0], encoding=sys.stdin.encoding) + os.sep + dfilename
        #dfilename = sys.path[0].rsplit('\\',1)[0] + '\\' + dfilename #Yavos: only useful for myself ;P
    dfilename = dfilename.replace('\\\\', '\\')
    dfilename = dfilename.replace('\\', os.sep)
    dfilename = dfilename.replace(os.sep + 'library.zip' + os.sep + '.','')

    directory = os.path.dirname(dfilename)
    if not os.path.exists(directory):
        os.makedirs(directory)
        __log__.info('Creating directory: '+directory)


    #Yavos: adding IrfanView-Handling
    if __config__.startIrfanSlide == True or __config__.startIrfanView == True:
        iv = True
        IrfanSlide = __config__.startIrfanSlide
        IrfanView = __config__.startIrfanView
    elif options.iv != None:
        iv = options.iv
        IrfanView = True
        IrfanSlide = False

    try:
        __dbManager__.createDatabase()

        if __config__.useList :
            listTxt = PixivListItem.parseList(__config__.downloadListDirectory+ os.sep + 'list.txt')
            __dbManager__.importList(listTxt)
            print "Updated " + str(len(listTxt)) + " items."

        if __config__.overwrite :
            msg = 'Overwrite enabled.'
            print msg
            __log__.info(msg)

        if __config__.dayLastUpdated != 0  and __config__.processFromDb:
            PixivHelper.printAndLog('info', 'Only process member where day last updated >= ' + str(__config__.dayLastUpdated))

        if __config__.dateDiff > 0:
            PixivHelper.printAndLog('info', 'Only process image where day last updated >= ' + str(__config__.dateDiff))

        if __config__.useBlacklistTags:
            global __blacklistTags
            __blacklistTags = PixivTags.parseTagsList("blacklist_tags.txt")
            PixivHelper.printAndLog('info', 'Using Blacklist Tags: ' + str(len(__blacklistTags)) + " items.")

        if __config__.useSuppressTags:
            global __suppressTags
            __suppressTags = PixivTags.parseTagsList("suppress_tags.txt")
            PixivHelper.printAndLog('info', 'Using Suppress Tags: ' + str(len(__suppressTags)) + " items.")

        username = __config__.username
        if username == '':
            username = raw_input('Username ? ')
        else :
            msg = 'Using Username: ' + username
            print msg
            __log__.info(msg)

        password = __config__.password
        if password == '':
            password = getpass.getpass('Password ? ')

        if npisvalid == True and np != 0: #Yavos: overwrite config-data
            msg = 'Limit up to: ' +  str(np) + ' page(s). (set via commandline)'
            print msg
            __log__.info(msg)
        elif __config__.numberOfPage != 0:
            msg = 'Limit up to: ' +  str(__config__.numberOfPage) + ' page(s).'
            print msg
            __log__.info(msg)

        ## Log in
        result = False
        if len(__config__.cookie) > 0:
            result = pixivLoginCookie()

        if not result:
            if __config__.useSSL:
                result = pixivLoginSSL(username,password)
            else:
                result = pixivLogin(username,password)

        if result:
            if __config__.overwrite :
                mode = PixivConstant.PIXIVUTIL_MODE_OVERWRITE
            else :
                mode = PixivConstant.PIXIVUTIL_MODE_UPDATE_ONLY

            while True:
                try:
                    if opisvalid: #Yavos (next 3 lines): if commandline then use it ;P
                        selection = op
                    else:
                        selection = menu()

                    if selection == '1':
                        menuDownloadByMemberId(mode, opisvalid, args)
                    elif selection == '2':
                        menuDownloadByImageId(mode, opisvalid, args)
                    elif selection == '3':
                        menuDownloadByTags(mode, opisvalid, args)
                    elif selection == '4':
                        menuDownloadFromList(mode, opisvalid, args)

                    elif selection == '5':
                        menuDownloadFromOnlineUserBookmark(mode, opisvalid, args)
                    elif selection == '6':
                        menuDownloadFromOnlineImageBookmark(mode, opisvalid, args)
                    elif selection == '7':
                        menuDownloadFromTagsList(mode, opisvalid, args)
                    elif selection == '8':
                        menuDownloadNewIllustFromBookmark(mode, opisvalid, args)
                    elif selection == '9':
                        menuDownloadByTitleCaption(mode, opisvalid, args)
                    elif selection == '10':
                        menuDownloadByTagAndMemberId(mode, opisvalid, args)
                    elif selection == '11':
                        menuDownloadByMemberBookmark(mode, opisvalid, args)
                    elif selection == '12':
                        menuDownloadByGroupId(mode, opisvalid, args)
                    elif selection == 'e':
                        menuExportOnlineBookmark(mode, opisvalid, args)
                    elif selection == 'd':
                        __dbManager__.main()
                    elif selection == 'r':
                        menuReloadConfigIni()
                    elif selection == 'p':
                        menuPrintConfigIni()
                    elif selection == '-all':
                        if npisvalid == False:
                            npisvalid = True
                            np = 0
                            print 'download all mode activated'
                        else:
                            npisvalid = False
                            print 'download mode reset to', __config__.numberOfPage, 'pages'
                    elif selection == 'x':
                        break

                    if ewd == True: #Yavos: added lines for "exit when done"
                        break
                    opisvalid = False #Yavos: needed to prevent endless loop
                except KeyboardInterrupt:
                    PixivHelper.printAndLog("info", "Keyboard Interrupt pressed, selection: " + selection)
                    PixivHelper.clearScreen()
                    print "Restarting..."
            if iv == True: #Yavos: adding IrfanView-handling
                PixivHelper.startIrfanView(__config__, dfilename, __config__.IrfanViewPath)
    except Exception as ex:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        ##__log__.error('Unknown Error: '+ str(exc_value))
        __log__.exception('Unknown Error: '+ str(exc_value))
    finally:
        __dbManager__.close()
        if ewd == False: ### Yavos: prevent input on exitwhendone
            if selection == None or selection != 'x' :
                raw_input('press enter to exit.')
        __log__.setLevel("INFO")
        __log__.info('EXIT')
        __log__.info('###############################################################')

if __name__ == '__main__':
    main()


