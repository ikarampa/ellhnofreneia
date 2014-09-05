# -*- coding:utf-8 -*-
import os, sys
sys.path.insert(0, os.path.abspath("./Ellhnofreneia/utils"))

import os.path, glob
import datetime
from utils import eyeD3
from urllib2 import urlopen, URLError, HTTPError
from pprint import pprint

FILENAME_PREFIX = r'Ellfren-'

if os.path.isdir('i:\\'):
    LOCAL_LIBRARY = r'I:\Music\Sorted\Comedy\Ellhnofreneia\Shows'
else:
    LOCAL_LIBRARY = r'W:\Music\Ellhnofreneia'

import time
def retry(ExceptionToCheck, tries=4, delay=3, backoff=1.1):
    """Retry decorator
    original from http://wiki.python.org/moin/PythonDecoratorLibrary#Retry
    """
    def deco_retry(f):
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            try_one_last_time = True
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                    try_one_last_time = False
                    break
                except ExceptionToCheck, e:
                    print "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            if try_one_last_time:
                return f(*args, **kwargs)
            return
        return f_retry  # true decorator
    return deco_retry

class Logger():
    def __init__(self, bQuiet=False):
        self.bQuiet = bQuiet
    def log(self, message):
        if not self.bQuiet:
            print message
            
class Library(Logger):
    def __init__(self):
        Logger.__init__(self)
        if not os.path.exists(LOCAL_LIBRARY):raise ValueError
        self.podcasts = {}
        self.log('Using library at:{0}'.format(LOCAL_LIBRARY))
        self.COMPRESS_SIZEMB_TRIGGER = 20
    def load(self):
        self.log("Loading podcasts")
        self.podcasts = {}
        print os.path.join(LOCAL_LIBRARY, '{0}*.mp3'.format(FILENAME_PREFIX))
        for infile in glob.glob(os.path.join(LOCAL_LIBRARY, '{0}*.mp3'.format(FILENAME_PREFIX))):
            filename = os.path.splitext(os.path.split(infile)[1])[0]
            podcastDate = filename.replace(FILENAME_PREFIX, '').split('_')
            pc = Podcast(podcastDate[0], podcastDate[1], podcastDate[2])
            self.podcasts[str('-'.join(podcastDate))] = pc
        self.log("Done loading podcasts")
    def getCount(self):
        self.load()
        return len(self.podcasts)
    def getPodcasts(self):
        self.load()
        return self.podcasts
    def getPodcastsSorted(self):
        self.load()
        sortedPodcasts = {}
        for dayMade in sorted(self.getPodcasts().keys()):
            sortedPodcasts[dayMade] = self.podcasts[dayMade]
        self.podcasts = sortedPodcasts
        return self.podcasts
    def checkURLs(self):
        for dayMade in sorted(self.getPodcasts().keys()):
            podcast = self.podcasts[dayMade]
            self.log('{0} {1} {2}'.format(dayMade, podcast.getURL(), podcast.existsRemote()))

    def podcastDownloadAllRecentMissing(self):
        downloads = 0
        currentDate = datetime.datetime.now()

        all_podcasts = []
        p = Podcast(currentDate.year, currentDate.month, currentDate.day)
        all_podcasts.append(p)
        while not p.existsLocal():  # and len(all_podcasts) < 15:
            currentDate = currentDate - datetime.timedelta(1)
            p = Podcast(currentDate.year, currentDate.month, currentDate.day)
            all_podcasts.append(p)

        print '{0} podcasts in the queue'.format(len(all_podcasts))
        pprint(all_podcasts)
        for pod in all_podcasts:
            self.log('Checking most recent {0} to \n\t\t {1}:'.format(p.getURL(), p.getLocalName()))
            if self.podcastDownload(pod):
                downloads += 1
                self.podcastTag(pod)
             
        self.log('Downloaded {0} podcast(s)'.format(downloads))
    def podcastDownloadFromDate(self, thisDate):
        p = Podcast(thisDate.year, thisDate.month, thisDate.day)
        self.downloadPodcast(p)
    @retry(Exception, 20, 5)
    def podcastDownload(self, podcast):
        from utils import wget
        
        if not podcast.isDownloadable():return False
        self.log('Downloading to "{0}"'.format(podcast.getLocalName()))
        
        try:
            wget.download(podcast.getURL(), podcast.getLocalName())
            
            self.podcastCompress(podcast)
            return True
        except UnicodeEncodeError as e:
            print e
        except Exception as e:
            self.log("Download error: {0} {1}".format(podcast.getURL(), e))
            os.remove(podcast.getLocalName())
            raise e
    def libraryCompress(self):
        from multiprocessing import cpu_count
        from threading import BoundedSemaphore, Thread
        MAX_THREADS = cpu_count()
        LOCK_semlock_oncompress = BoundedSemaphore(MAX_THREADS)
        class ThreadedCompress(Thread):
            def __init__(self, compressor, tagger, podcast):
                Thread.__init__(self)
                self.compressor = compressor
                self.podcast = podcast
                self.tagger = tagger
            def __del__(self):
                LOCK_semlock_oncompress.release()
            def run(self):
                LOCK_semlock_oncompress.acquire()
                self.compressor(self.podcast)
                self.tagger(self.podcast)
                
        for p in self.getPodcasts().values():
            t = ThreadedCompress(self.podcastCompress, self.podcastTag, p)
            t.start()
                        
    def podcastCompress(self, podcast, volumeGain=800 , constant=False):
        if podcast.getSizeMB() < 10 or podcast.getSizeMB() <= self.COMPRESS_SIZEMB_TRIGGER:
            return
        if constant:
            raise Exception('Not implemented')
        compressors = {  # 'LAME':'lame -h -a --preset cbr 64 --mp3input {0} {1}',
                     'LAME':'lame -h -a --clipdetect --verbose -q 0 -V 5 --mp3input {0} {1}',
                     'FFMPEG':'ffmpeg -i {0} -ac 1 -ab 64000 -f mp3 -vol {2} {1}',  # Works on FFmpeg version SVN-r22292-xuggle-4.0.845
                    'AACGAIN':'aacgain -r -p -t -k {0}'
                    """
                    The above command will adjust track to 89dB volume. 
                    -k means automatically lower this number if clipping may occur, 
                    -t is required to make the file as compatible as possible with 
                        different players (iPod Shuffle may have problems otherwise), 
                    -p means preserve timestamp of file (optional). 
                    Also during converting, it will create temporary files (because of -t) 
                    """
                    }

        cmd = compressors['LAME'].format(podcast.getLocalName(),
                                            podcast.getLocalNameShadow(),
                                            volumeGain)
        gain = compressors['AACGAIN'].format(podcast.getLocalNameShadow())
        print 'Compression command: {0}'.format(cmd)
        compressionResult = (os.system(cmd) == 0)
#         print 'Gain command: {0}'.format(gain)
#         gainResult = (os.system(gain) == 0)
        if compressionResult and (os.path.getsize(podcast.getLocalNameShadow()) < podcast.getSize):
            try:
                self._fileRename(podcast.getLocalName(), podcast.getLocalNameBackup())
                self._fileRename(podcast.getLocalNameShadow(), podcast.getLocalName())
                self._fileDelete(podcast.getLocalNameBackup())
            except Exception, e:
                self.log('Failed renaming compressed file:\n{0}\n{1}\n{2}'.format(podcast.getLocalNameBackup(),
                                                                                    podcast.getLocalNameShadow(),
                                                                                    podcast.getLocalName()),
                                                                                    e)
        if not compressionResult:
            self.__fileDelete(podcast.getLocalNameShadow())
    def podcastsCompressBig(self):
        for p in self.getPodcastsSorted().values():
            self.podcastCompress(p)

    def podcastTag(self , podcast):
#        podcast.setTag( genre = 'Comedy',
#                        trackNumber = self.getCount() )
        podcast.setTag(artist=u'Αποστόλης - Θύμιος',
                        album=u'Ελληνοφρένεια',
                        genre='Comedy',
                        trackNumber=self.getCount())
    def _fileRename(self, filename_withpath, filenameNew_withpath):
        attempt = 0
        self.log('Renaming {0} to {1}'.format(filename_withpath , filenameNew_withpath))
        while not os.path.isfile(filenameNew_withpath):
            try:
                os.rename(filename_withpath, filenameNew_withpath)
            except Exception:
                attempt += 1
                self.log('Could not rename ({1}): {0}'.format(filename_withpath, attempt))

    def _fileDelete(self, filename_withpath):
        attempt = 0
        self.log('Deleting {0}'.format(filename_withpath))
        while os.path.isfile(filename_withpath):
            try:
                os.remove(filename_withpath)
            except Exception:
                attempt += 1
                self.log('Could not delete ({1}): {0}'.format(filename_withpath, attempt))

class Podcast(Logger):
    def __init__(self, year, month, day , localFileName='' , bQuiet=False):
        Logger.__init__(self)
        self.bQuiet = bQuiet
        self.bday = datetime.date(int(year), int(month), int(day))  # Broadcast day
        self.URL_CHECK_TIMEOUT = 20
        self.url_overriden = ''
        self.urlFormat = 'http://www.ellinofreneianet.gr/podcast/{2}{1}{5}.mp3'

        if localFileName:
            self.localFileName = os.path.splitext(os.path.split(localFileName)[1])[0]
        else:
            self.localFileName = ''
    def __repr__(self):
        return '<Podcast: {0}>'.format(self.bday)
    
    def getURL(self):
        days_greek = {1:['DEYTERA'], 2:['TRITi','TRITH'], 
                      3:['TETARTH'], 4:['PEMPTi','PEMPTI'], 
                      5:['PARASKEYI','PARASKEYi','PARASKEYIok'], 0:[''], 6:['']}
        
        for day in days_greek[int(self.bday.strftime('%w').lower())]:
            url_podcast=self.urlFormat.format(self.bday.year,
                                              self.bday.strftime('%m'),
                                              self.bday.day,
                                              self.bday.strftime('%y'),
                                              self.bday.strftime('%A').lower(),
                                              day)
            final_url=url_podcast
            if self.existsRemote(customUrl=url_podcast):
                return final_url
                
        return self.url_overriden or final_url
    def setURL(self , url_overriden):
        self.url_overriden = url_overriden
    def getLocalName(self):
        return self.localFileName or os.path.join(LOCAL_LIBRARY,
                                                  '{3}{0}_{1:02d}_{2:02d}.mp3'.format(self.bday.year,
                                                                                      self.bday.month,
                                                                                      self.bday.day,
                                                                                      FILENAME_PREFIX))
    def getLocalNameShadow(self):
        return '{0}.tmp.mp3'.format(self.getLocalName())
    def getLocalNameBackup(self):
        return '{0}.bak'.format(self.getLocalName())
    def getSizeMB(self):
        if self.existsLocal():
            return os.path.getsize(self.getLocalName()) / 1024.0 ** 2
        else:
            return 0
    def getSize(self):
        
        if os.path.isfile(self.getLocalName()):
            return os.path.getsize(self.getLocalName())
        else:
            return 0
    def getTag(self):
        if not self.existsLocal():return False
        tag = eyeD3.Tag()
        tag.link(self.getLocalName())
        return tag
    def setTag(self, artist='', album='', genre='', trackNumber=0):
        if not self.existsLocal():return False
        tag = eyeD3.Tag()
        tag.link(self.getLocalName())
        tag.header.setVersion(eyeD3.ID3_V2_3)
        tag.setArtist(artist)
        tag.setAlbum(album)
        tag.setGenre(genre)
        title = u'Show {0}-{1:02d}-{2:02d}'.format(self.bday.year, self.bday.month, self.bday.day)
        tag.setTitle(title)
        tag.setDate(year=self.bday.year,
                     month=self.bday.month,
                     dayOfMonth=self.bday.day)
        tag.setTrackNum((trackNumber, None))
        tag.addLyrics(self.getURL())
        tag.update()
        self.log('Tagged podcast {0} / {1} / {2}'.format(artist, album, title))
        return True
    def isDownloadable(self):
        return self.bday.weekday() < 5 and (not self.existsLocal()) and self.existsRemote()
    
    def existsLocal(self):
        return os.path.isfile(self.getLocalName()) and (self.getSize()> 0)

    @retry(URLError, 2, 0)
    def existsRemote(self , customUrl='', bQuiet=True, overrideTIMEOUT=None):
        try:
            url_tocheck=customUrl or self.getURL()
            if url_tocheck=='':return False
            code = urlopen(url_tocheck, timeout=overrideTIMEOUT or self.URL_CHECK_TIMEOUT).code
            return (0 < code / 100 < 4)
        except HTTPError, e:
            print  "HTTP Error:", e.code , url_tocheck
        except URLError, e:
            print  "URL Error: {0} {1} Timeout={2}".format(e.reason, url_tocheck, self.URL_CHECK_TIMEOUT)
            if 'timed out' in e.reason:
                self.URL_CHECK_TIMEOUT = 2 * self.URL_CHECK_TIMEOUT
        return False
    
    
    def test(self):
        tag = eyeD3.Tag()
        tag.link(self.getLocalName())

        print 'Artist', tag.getArtist()
        print 'Album', tag.getAlbum()
        print 'Title', tag.getTitle()

def downloadnow():
    now = datetime.datetime.now()
    p = Podcast(now.year, now.month, now.day)
    myL = Library()
    myL.podcastDownloadAllRecentMissing()

if __name__ == '__main__':
    downloadnow()
