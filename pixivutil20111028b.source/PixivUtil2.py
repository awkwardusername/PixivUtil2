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
from PixivModel import PixivArtist, PixivModelException, PixivImage, PixivListItem, PixivBookmark, PixivTags

##import pprint

Yavos = True
npisvalid = False
np = 0
opisvalid = False
op = ''

from optparse import OptionParser
import datetime
import codecs
import subprocess

__cj__ = cookielib.LWPCookieJar()
__br__ = Browser(factory=mechanize.RobustFactory())
__br__.set_cookiejar(__cj__)

gc.enable()
##gc.set_debug(gc.DEBUG_LEAK)

__dbManager__ = PixivDBManager.PixivDBManager()
__config__    = PixivConfig.PixivConfig()
    
### Set up logging###
__log__ = logging.getLogger('PixivUtil'+PixivConstant.PIXIVUTIL_VERSION)
__log__.setLevel(logging.DEBUG)

__logHandler__ = logging.handlers.RotatingFileHandler(PixivConstant.PIXIVUTIL_LOG_FILE, maxBytes=1024000, backupCount=5)
__formatter__  = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
__logHandler__.setFormatter(__formatter__)
__log__.addHandler(__logHandler__)

## http://www.pixiv.net/member_illust.php?mode=medium&illust_id=18830248
__re_illust = re.compile(r'member_illust.*illust_id=(\d*)')
##__re_manga_page = re.compile(r'(_p\d+)\.');

### Utilities function ###
def clearall():
    all = [var for var in globals() if (var[:2], var[-2:]) != ("__", "__") and var != "clearall"]
    for var in all:
        del globals()[var]

def dumpHtml(filename, html):
    try:
        dump = file(filename, 'wb')
        dump.write(html)
        dump.close()
    except :
        pass

def printAndLog(level, msg):
    print msg
    if level == 'info':
        __log__.info(msg)
    elif level == 'error':
        __log__.error(msg)

#-T04------For download file
def downloadImage(url, filename, referer, overwrite, retry):
    try:
        print 'Start downloading...',
        try:
            req = urllib2.Request(url)

            if referer != None:
                req.add_header('Referer', referer)

            br2 = Browser()
            br2.set_cookiejar(__cj__)
            if __config__.useProxy:
                br2.set_proxies(__config__.proxy)
            br2.set_handle_robots(__config__.useRobots)
            
            res = br2.open(req)
            try:
                filesize = res.info()['Content-Length']
            except KeyError:
                filesize = 0
            except:
                raise

            if not overwrite and os.path.exists(filename) and os.path.isfile(filename) :
                if int(filesize) == os.path.getsize(filename) :
                    print "\tFile exist! (Identical Size)"
                    return 0 #Yavos: added 0 -> updateImage() will be executed
                else :
                    print "\t Found file with different filesize, removing..."
                    os.remove(filename)
            
            directory = os.path.dirname(filename)
            if not os.path.exists(directory):
                os.makedirs(directory)
                __log__.info('Creating directory: '+directory)

            try:
                save = file(filename + '.pixiv', 'wb+', 4096)
            except IOError:
                msg = 'Error at downloadImage(): Cannot save ' + url +' to ' + filename + ' ' + str(sys.exc_info())
                PixivHelper.safePrint(msg)
                __log__.error(unicode(msg))
                save = file(os.path.split(url)[1], 'wb+', 4096)

            prev = 0
            print '{0:22} Bytes'.format(prev),
            try:
                while 1:
                    save.write(res.read(4096))
                    curr = save.tell()
                    print '\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b\b',
                    print '{0:9} of {1:9} Bytes'.format(curr, filesize),
                    if curr == prev:
                        break
                    prev = curr
                if iv == True or __config__.createDownloadLists == True:
                    dfile = codecs.open(dfilename, 'a+', encoding='utf-8')
                    dfile.write(filename + "\n")
                    dfile.close()
            finally:
                save.close()
                if overwrite and os.path.exists(filename):
                    os.remove(filename)
                os.rename(filename + '.pixiv', filename)
                del save
                del req
                del res
        except urllib2.HTTPError as httpError:
            print httpError
            print str(httpError.code)
            __log__.error('HTTPError: '+ str(httpError))
            if httpError.code == 404:
                return -1
            raise
        except urllib2.URLError as urlError:
            print urlError
            __log__.error('URLError: '+ str(urlError))
            raise

        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback)
            __log__.error('Error at downloadImage(): ' + str(sys.exc_info()))
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
        
def configBrowser():
    if __config__.useProxy:
        __br__.set_proxies(__config__.proxy)
    __br__.set_handle_equiv(True)
    #__br__.set_handle_gzip(True)
    __br__.set_handle_redirect(True)
    __br__.set_handle_referer(True)
    __br__.set_handle_robots(__config__.useRobots)
    __br__.set_debug_http(__config__.debugHttp)
    __br__.visit_response
    __br__.addheaders = [('User-agent', __config__.useragent)]

    socket.setdefaulttimeout(__config__.timeout)

def loadCookie(cookieValue):
    '''Load cookie to the Browser instance'''
    ck = cookielib.Cookie(version=0, name='PHPSESSID', value=cookieValue, port=None, port_specified=False, domain='pixiv.net', domain_specified=False, domain_initial_dot=False, path='/', path_specified=True, secure=False, expires=None, discard=True, comment=None, comment_url=None, rest={'HttpOnly': None}, rfc2109=False)
    __cj__.set_cookie(ck)
    
### Pixiv related function ###
def pixivLogin(username, password):
    '''Log in to Pixiv, return 0 if success'''
    printAndLog('info','logging in')

    ## try log in with cookie
    cookieValue = __config__.cookie
    if len(cookieValue) > 0:
        printAndLog('info','Trying to log with saved cookie')
        loadCookie(cookieValue);
        req = urllib2.Request('http://www.pixiv.net/mypage.php')
        __br__.open(req)
        if __br__.response().geturl() == 'http://www.pixiv.net/mypage.php' :
            print 'done.'
            __log__.info('Logged in')
            return 0
        else :
            printAndLog('info','Cookie already expired/invalid.')

    try:
        printAndLog('info','Log in using form.')
        req = urllib2.Request(PixivConstant.PIXIV_URL+PixivConstant.PIXIV_LOGIN_URL)
        __br__.open(req)
        
        form = __br__.select_form(nr=PixivConstant.PIXIV_FORM_NUMBER)
        __br__['pixiv_id'] = username
        __br__['pass'] = password

        response = __br__.submit()
        if response.geturl() == 'http://www.pixiv.net/mypage.php':
            print 'done.'
            __log__.info('Logged in')
            ## write back the new cookie value
            for cookie in  __br__._ua_handlers['_cookies'].cookiejar:
                if cookie.name == 'PHPSESSID':
                    print 'new cookie value:', cookie.value
                    __config__.cookie = cookie.value
                    __config__.writeConfig()
                    break                
            return 0
        else :
            printAndLog('info','Wrong username or password.')
            return 1
    except:
        print 'Error at pixivLogin():',sys.exc_info()
        print 'failed'
        __log__.error('Error at pixivLogin(): ' + str(sys.exc_info()))
        raise

def processList(mode):
    result = None
    try:
        ## Getting the list
        if __config__.processFromDb :
            printAndLog('info','Processing from database.')
            if __config__.dayLastUpdated == 0:
                result = __dbManager__.selectAllMember()
            else :
                print 'Select only last',__config__.dayLastUpdated, 'days.'
                result = __dbManager__.selectMembersByLastDownloadDate(__config__.dayLastUpdated)
        else :
            printAndLog('info','Processing from list file.')
            listFilename = __config__.downloadListDirectory + '\\list.txt'
            if op == '4' and len(args) > 0:
                testListFilename = __config__.downloadListDirectory + '\\' + args[0]
                if os.path.exists(testListFilename) :
                    listFilename = testListFilename
            result = PixivListItem.parseList(listFilename, __config__.rootDirectory)

        print "Found "+str(len(result))+" items."

        ## iterating the list
        for item in result:
            retryCount = 0
            while True:
                try:
                    processMember(mode, item.memberId, item.path)
                    break
                except:
                    if retryCount > __config__.retry:
                        printAndLog('error','Giving up member_id: '+str(row[0]))
                        break
                    retryCount = retryCount + 1
                    print 'Something wrong, retrying after 2 second (', retryCount, ')'
                    time.sleep(2)
            
            __br__.clear_history()
            print 'done.'

    except:
        print 'Error at processList():',sys.exc_info()
        print 'failed'
        __log__.error('Error at processList(): ' + str(sys.exc_info()))
        raise

def processMember(mode, member_id, userDir=''): #Yavos added dir-argument which will be initialized as '' when not given
    printAndLog('info','Processing Member Id: ' + str(member_id))
    __config__.loadConfig()

    try:
        page = 1
        noOfImages = 1
        avatarDownloaded = False

        while True:
            print 'Page ',page
            ## Try to get the member page
            while True:
                try:
                    listPage = __br__.open('http://www.pixiv.net/member_illust.php?id='+str(member_id)+'&p='+str(page))
                    artist = PixivArtist(mid=member_id, page=BeautifulSoup(listPage.read()))
                    break
                except PixivModelException as ex:
                    print 'Error:',ex
                    return
                except Exception as ue:
                    print ue
                    repeat = range(1,__config__.retryWait)
                    for t in repeat:
                        print t,
                        time.sleep(1)
                    print ''
            print 'Member Name  :', PixivHelper.safePrint(artist.artistName)
            print 'Member Avatar:', artist.artistAvatar
            print 'Member Token :', artist.artistToken

            if artist.artistAvatar.find('no_profile') == -1 and avatarDownloaded == False and __config__.downloadAvatar :
                ## Download avatar as folder.jpg
                filenameFormat = __config__.filenameFormat
                if userDir == '':
                    targetDir = __config__.rootDirectory
                else:
                    targetDir = userDir
                filenameFormat = filenameFormat.split('\\')[0]
                image = PixivImage(parent=artist)
                filename = PixivHelper.makeFilename(filenameFormat, image, tagsSeparator=__config__.tagsSeparator)
                filename = PixivHelper.sanitizeFilename(filename)
                filename = targetDir + '\\' + filename + '\\' + 'folder.jpg'
                filename = filename.replace('\\\\', '\\')
                result = downloadImage(artist.artistAvatar, filename, listPage.geturl(), __config__.overwrite, __config__.retry)
                avatarDownloaded = True
            
            __dbManager__.updateMemberName(member_id, artist.artistName)

            updatedLimitCount = 0
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
                        processImage(mode, artist, image_id, userDir) #Yavos added dir-argument to pass
                        __dbManager__.insertImage(member_id, image_id)
                        break
                    except Exception as ex:
                        if retryCount > __config__.retry:
                            printAndLog('error', "Giving up image_id: "+str(image_id)) 
                            return
                        retryCount = retryCount + 1
                        print "Stuff happened, trying again after 2 second (", retryCount,")"
                        print ex
                        time.sleep(2)

                noOfImages = noOfImages + 1
            page = page + 1

            del artist
            del listPage
            __br__.clear_history()
            gc.collect()

            if npisvalid == True: #Yavos: overwriting config-data
                if page > np and np != 0:
                    break
            elif page > __config__.numberOfPage and __config__.numberOfPage != 0 :
                break
        __dbManager__.updateLastDownloadedImage(member_id, image_id)
        print 'Done.\n'
        __log__.info('Member_id: ' + str(member_id) + ' complete, last image_id: ' + str(image_id))
    except:
        printAndLog('error', 'Error at processMember(): ' + str(sys.exc_info()))
        try: 
            if listPage != None :
                dumpHtml('Error page for member ' + str(member_id) + '.html', listPage.get_data())
        except:
            printAndLog('error', 'Cannot dump page for member_id:'+str(member_id))
        raise

def processImage(mode, artist=None, image_id=None, userDir=''): #Yavos added dir-argument which will be initialized as '' when not given
    try:
        print 'Processing Image Id:', image_id
        ## already downloaded images won't be downloaded twice - needed in processImage to catch any download
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
                image = PixivImage(iid=image_id, page=parseMediumPage, parent=artist)
                parseMediumPage.decompose()
                del parseMediumPage
                break
            except PixivModelException as ex:
                print ex
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
                    if mediumPage != None :
                        dumpHtml('Error page for image ' + str(image_id) + '.html', mediumPage.get_data())
                    return
        print "Title:", PixivHelper.safePrint(image.imageTitle)
        print "Tags :", PixivHelper.safePrint(', '.join(image.imageTags))
        print "Mode :", image.imageMode
        
        errorCount = 0
        while True:
            try :
                bigUrl = 'http://www.pixiv.net/member_illust.php?mode='+image.imageMode+'&illust_id='+str(image_id)
                viewPage = __br__.follow_link(url_regex='mode='+image.imageMode+'&illust_id='+str(image_id))
                parseBigImage = BeautifulSoup(viewPage.read())
                image.ParseImages(page=parseBigImage)
                parseBigImage.decompose()
                del parseBigImage
                break
            except PixivModelException as ex:
                printAndLog('info', str(ex))
                return
            except urllib2.URLError as ue:
                if errorCount > __config__.retry:
                    printAndLog('error', 'Giving up image_id: '+str(image_id))
                    return
                errorCount = errorCount + 1
                print ue
                repeat = range(1,__config__.retryWait)
                for t in repeat:
                    print t,
                    time.sleep(1)
                print ''

        result = 0
        skipOne = False
        for img in image.imageUrls:
            if skipOne:
                skipOne = False
                continue
            print 'Image URL :', img
            url = os.path.basename(img)
            splittedUrl = url.split('.')
            if splittedUrl[0].startswith(str(image_id)):
                imageExtension = splittedUrl[1]
                imageExtension = imageExtension.split('?')[0]

                #Yavos: filename will be added here if given in list
                filenameFormat = __config__.filenameFormat
                if userDir == '': #Yavos: use config-options
                    targetDir = __config__.rootDirectory
                else: #Yavos: use filename from list
                    targetDir = userDir

                filename = PixivHelper.makeFilename(filenameFormat, image, tagsSeparator=__config__.tagsSeparator)
                if image.imageMode == 'manga':
                    filename = filename.replace(str(image_id), str(splittedUrl[0]))
                filename = filename + '.' + imageExtension
                filename = PixivHelper.sanitizeFilename(filename)
                filename = targetDir + '\\' + filename
                filename = filename.replace('\\\\', '\\') #prevent double-backslash in case dir or rootDirectory has an ending \

                if image.imageMode == 'manga' and __config__.createMangaDir :
                    mangaPage = filename.split("_p");##__re_manga_page.findall(filename)
                    filename = mangaPage[0] + "\\_p" + mangaPage[1]
                    
                print 'Filename  :', PixivHelper.safePrint(filename)
                result = -1
   
                if mode == PixivConstant.PIXIVUTIL_MODE_OVERWRITE:
                    result = downloadImage(img, filename, viewPage.geturl(), True, __config__.retry)
                else:
                    result = downloadImage(img, filename, viewPage.geturl(), False, __config__.retry)
                print ''

            if result == -1 and image.imageMode == 'manga' and img.find('_big') > -1:
                print 'No big manga image available, try the small one'
            elif result == 0 and image.imageMode == 'manga' and img.find('_big') > -1:
                skipOne = True
            elif result == -1:
                printAndLog('error', 'Image url not found: '+str(image.imageId))
                
        ## Only save to db if all images is downloaded completely
        if result == 0 :
            try:
                __dbManager__.insertImage(image.artist.artistId, image.imageId)
            except:
                pass
            __dbManager__.updateImage(image.imageId, image.imageTitle, filename)
        else:
            print "something happen."

        del viewPage
        del mediumPage
        del image

        gc.collect()
        ##clearall()
        print '\n'

    except:
        print 'Error at processImage():',str(sys.exc_info())
        __log__.error('Error at processImage(): ' + str(sys.exc_info()))
        try:
            dumpHtml('image_'+str(image_id)+'.html', mediumPage.get_data())
        except:
            printAndLog('error', 'Cannot dump page for image_id: '+str(image_id))
        raise

def processTags(mode, tags, page=1):
    try:
        msg = 'Searching for tags '+tags
        print msg
        __log__.info(msg)
        if not tags.startswith("%") :
            ## Encode the tags
            tags = urllib.quote_plus(tags.decode(sys.stdout.encoding).encode("utf8"))
        i = page
        images = 1
        
        while True:
            url = 'http://www.pixiv.net/search.php?s_mode=s_tag&p='+str(i)+'&word='+tags
            print 'Looping... for '+ url
            searchPage = __br__.open(url)

            parseSearchPage = BeautifulSoup(searchPage.read())
            t = PixivTags()
            l = t.parseTags(parseSearchPage)
            
            if len(l) == 0 :
                print 'No more images'
                break
            else:
                for image_id in l:
                    print 'Image #'+str(images)
                    print 'Image id:', image_id
                    while True:
                        try:
                            processImage(mode, None, image_id)
                            break;
                        except httplib.BadStatusLine:
                            print "Stuff happened, trying again after 2 second..."
                            time.sleep(2)
                        
                    images = images + 1

            __br__.clear_history()

            i = i + 1

            parseSearchPage.decompose()
            del parseSearchPage
            del searchPage

            if npisvalid == True: #Yavos: overwrite config-data
                if i > np and np != 0:
                    break
            elif i > __config__.numberOfPage and __config__.numberOfPage != 0 :
                break
        print 'done'
    except:
        print 'Error at processTags():',sys.exc_info()
        __log__.error('Error at processTags(): ' + str(sys.exc_info()))
        raise

def processTagsList(mode, filename, page=1):
    try:
        print "Reading",filename
        l = PixivTags.parseTagsList(filename)
        for tag in l:
            processTags(mode, tag, page)
    except:
        print 'Error at processTagsList():',sys.exc_info()
        __log__.error('Error at processTagsList(): ' + str(sys.exc_info()))
        raise
    
def processBookmark(mode):
    try:
        print "Importing Bookmarks..."
        totalList = list()
        i = 1
        while True:
            page = __br__.open('http://www.pixiv.net/bookmark.php?type=user&p='+str(i))
            parsePage = BeautifulSoup(page.read())
            l = PixivBookmark.parseBookmark(parsePage)
            if len(l) == 0:
                break
            totalList.extend(l)
            i = i + 1
        print "Result: ", str(len(totalList)), "items."        
        for item in totalList:
            processMember(mode, item.memberId, item.path)

    except :
        print 'Error at processBookmark():',sys.exc_info()
        __log__.error('Error at processBookmark(): ' + str(sys.exc_info()))
        raise

def exportBookmark(filename):
    try:
        print "Importing Bookmarks..." 
        totalList = list()
        i = 1
        while True:
            page = __br__.open('http://www.pixiv.net/bookmark.php?type=user&p='+str(i))
            parsePage = BeautifulSoup(page.read())
            l = PixivBookmark.parseBookmark(parsePage)
            if len(l) == 0:
                break
            totalList.extend(l)
            i = i + 1
        print "Result: ", str(len(totalList)), "items."
        PixivBookmark.exportList(totalList, filename)
    except :
        print 'Error at exportBookmark():',sys.exc_info()
        __log__.error('Error at exportBookmark(): ' + str(sys.exc_info()))
        raise
    
def header():
    print 'PixivDownloader2 version', PixivConstant.PIXIVUTIL_VERSION
    print PixivConstant.PIXIVUTIL_LINK
    
def menu():
    header()
    print '1. Download by member_id'
    print '2. Download by image_id'
    print '3. Download by tags'
    print '4. Download from list'
    print '5. Download from bookmark'
    print '6. Download from tags list'
    print '------------------------'
    print 'd. Manage database'
    print 'e. Export bookmark'
    print 'x. Exit'
    
    return raw_input('Input: ')

### Main thread ###
def main():
    header()
    
    ## Option Parser
    global npisvalid
    global opisvalid
    global np
    global iv
    global op
    
    parser = OptionParser()
    parser.add_option('-s', '--startaction', dest='startaction', help='Action you want to load your program with: 1 "Download by member_id", 2 - "Download by image_id", 3 - "Download by tags", 4 - "Download from list", 5 - "Manage database"')
    parser.add_option('-x', '--exitwhendone', dest='exitwhendone', help='Exit programm when done. (only useful when not using DB-Manager)', action='store_true', default=False)
    parser.add_option('-i', '--irfanview', dest='iv', help='start IrfanView after downloading images using downloaded_on_%date%.txt', action='store_true', default=False)
    parser.add_option('-n', '--numberofpages', dest='numberofpages', help='overwrites numberOfPage set in config.ini')

    (options, args) = parser.parse_args()

    op = options.startaction
    if op in ('1', '2', '3', '4', '5'):
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
    
    __log__.info('Starting...')
    try:
        __config__.loadConfig()
    except:
        print 'Failed to read configuration.'
        __log__.error('Failed to read configuration.')

    configBrowser()
    selection = None
    global dfilename
    
    #Yavos: adding File for downloadlist
    now = datetime.date.today()
    dfilename = __config__.downloadListDirectory + '\\' + 'Downloaded_on_' + now.strftime('%Y-%m-%d') + '.txt'
    if not re.match(r'[a-zA-Z]:', dfilename):
        dfilename = sys.path[0] + '\\' + dfilename
        #dfilename = sys.path[0].rsplit('\\',1)[0] + '\\' + dfilename #Yavos: only useful for myself ;P
    dfilename = dfilename.replace('\\\\', '\\')
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
            listTxt = PixivListItem.parseList(__config__.downloadListDirectory+'\\list.txt')
            __dbManager__.importList(listTxt)
            print "Updated " + str(len(listTxt)) + " items."

        if __config__.useProxy :
            msg = 'Using proxy: ' + __config__.proxyAddress
            print msg
            __log__.info(msg)

        if __config__.debugHttp :
            msg = 'Debug HTTP enabled.'
            print msg
            __log__.info(msg)

        if __config__.overwrite :
            msg = 'Overwrite enabled.'
            print msg
            __log__.info(msg)

        if __config__.dayLastUpdated != 0  and __config__.processFromDb:
            msg = 'Only process member where day last updated >= ' + str(__config__.dayLastUpdated)
            print msg
            __log__.info(msg)

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

        result = pixivLogin(username,password)

        if result == 0 :            
            if __config__.overwrite :
                mode = PixivConstant.PIXIVUTIL_MODE_OVERWRITE
            else :
                mode = PixivConstant.PIXIVUTIL_MODE_UPDATE_ONLY

            while True:
                if opisvalid: #Yavos (next 3 lines): if commandline then use it ;P
                    selection = op
                else:
                    selection = menu()
                if selection == '1':
                    __log__.info('Member id mode.')
                    if opisvalid and len(args) > 0: #Yavos: adding new lines
                        #print "there are", len(args), "arguments"
                        for member_id in args:
                            try:
                                testID = int(member_id)
                                #print "ID", member_id, "is valid"
                            except:
                                print "ID", member_id, "is not valid"
                                continue
                            processMember(mode, int(member_id))
                    else: #Yavos: end
                        member_id = raw_input('Member id: ')
                        processMember(mode, member_id.strip())
                elif selection == '2':
                    __log__.info('Image id mode.')
                    if opisvalid and len(args) > 0: #Yavos: start
                        for image_id in args:
                            try:
                                testID = int(image_id)
                                #print "ID", image_id, "is valid"
                            except:
                                print "ID", image_id, "is not valid"
                                continue
                            processImage(mode, None, int(image_id))
                    else:
                        image_id = raw_input('Image id: ')
                        processImage(mode, None, int(image_id)) #Yavos: end
                elif selection == '3':
                    __log__.info('tags mode.')
                    page = 1
                    if opisvalid and len(args) > 0: #Yavos: start
                        tags = " ".join(args)
                    else:
                        tags = raw_input('Tags: ') #Yavos: end
                        page  = raw_input('Start Page: ') or 1
                    processTags(mode, tags, int(page))
                elif selection == '4':
                    __log__.info('Batch mode.')
                    processList(mode)
                elif selection == '5':
                    __log__.info('Bookmark mode.')
                    processBookmark(mode)
                elif selection == '6':
                    __log__.info('Taglist mode.')
                    filename = raw_input("Tags list filename: ")
                    page  = raw_input('Start Page: ') or 1
                    processTagsList(mode, filename, int(page))
                elif selection == 'e':
                    __log__.info('Export Bookmark mode.')
                    filename = raw_input("Filename: ")
                    exportBookmark(filename)
                elif selection == 'd':
                    __dbManager__.main()
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
            if iv == True: #Yavos: adding IrfanView-handling
                print 'starting IrfanView...'
                if os.path.exists(dfilename):
                    ivpath = __config__.IrfanViewPath + '\\i_view32.exe' #get first part from config.ini
                    ivpath = ivpath.replace('\\\\', '\\')                    
                    info = None
                    if IrfanSlide == True:
                        info = subprocess.STARTUPINFO()
                        info.dwFlags = 1
                        info.wShowWindow = 6 #start minimized in background (6)
                        ivcommand = ivpath + ' /slideshow=' + dfilename
                        subprocess.Popen(ivcommand)
                    if IrfanView == True:
                        ivcommand = ivpath + ' /filelist=' + dfilename
                        subprocess.Popen(ivcommand, startupinfo=info)
                else:
                    print 'could not load', dfilename

    except Exception as ex:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        __log__.error('Unknown Error: '+ str(exc_value))
    finally:
        __dbManager__.close()
        if ewd == False: ### Yavos: prevent input on exitwhendone
            if selection == None or selection != 'x' :
                raw_input('press enter to exit.')
        __log__.info('EXIT')

if __name__ == '__main__':
    main()
    