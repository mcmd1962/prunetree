#!/usr/bin/python
# vim: set autoindent filetype=python tabstop=3 shiftwidth=3 softtabstop=3 number textwidth=175 expandtab:

import datetime
import os
import sys
import re
import logging
import hashlib
import argparse
import pdb
import json
import time

####
# prunetree.py, Max Bisschop 27 Sept 2015 (V1.0)
# Will scan all files in dictionary, more than minFSize in size
# If files are same size, calculate Digest
# If Digest are the same, delete the copies and create hard link instead

###
# Global definitions and configs


# Command line options:
# Command line arguments
description = 'Tool to change identical files (based on digest checksums) into hard links to safe diskspace'
epilog      = '''
_______________________________________________________________________________
This tool will first store all sizes and file names in a dictionary and
than per size with more than 1 file try to deduplicate this.

The procedure to do this is as follows:
* First the tool will find all files per directory. In this phase it will collect:
  . filename
  . filesize
  . inode
* Than it will remove all entries in the collected list which have only 1 file per size
* Than it will calculate the digests per inode (not per file!)
* For files with identical digests, it will replace the file with hard links.

'''

parser = argparse.ArgumentParser(description = description, epilog =
epilog, formatter_class = argparse.RawDescriptionHelpFormatter)
parser.add_argument('-d', '--debug',
                  dest    = 'debug',
                  action  = 'store_true',
                  default = False,
                  help    = "used for debugging code"
                 )

choices = hashlib.algorithms
parser.add_argument('-a', '--algorithm',
                  dest    = 'algorithm',
                  type    = str,
                  choices = choices,
                  default = 'md5',
                  help    = "hash algorithm, any of " + ", ".join(choices) + ". Defaults to '%(default)s'.",
                  metavar = "HASH"
                 )

choices = ['debug', 'info', 'warning', 'error', 'critical']
parser.add_argument('-l', '--loglevel',
                  dest    = 'loglevel',
                  type    = str,
                  choices = choices,
                  default = 'info',
                  help    = "loglevel, any of " + ", ".join(choices) + ". Defaults to '%(default)s'.",
                  metavar = "LOGLEVEL"
                 )

parser.add_argument('-n', '--dry-run', '--dryrun',
                  dest    = 'DryRun',
                  action  = 'store_true',
                  default = False,
                  help    = "dry-run mode, do not make changes, defaults to '%(default)s'."
                 )

parser.add_argument('--updates',
                  dest    = 'updates',
                  type    = int,
                  default = 5,
                  help    = "How often update messages will be shown in the investigation phase, defaults to '%(default)s'.",
                  metavar = 'SECONDS'
                 )

parser.add_argument('--minFSize',
                  dest    = 'minFSize',
                  type    = int,
                  default = 4096,
                  help    = "Minimum file size, do not consider files less than these # of bytes to prune, defaults to '%(default)s'.",
                  metavar = 'SIZE'
                 )

parser.add_argument('--maxFSize',
                  dest    = 'maxFSize',
                  type    = int,
                  default = 800 * 1024 * 1024,
                  help    = "Maximum file size, do not consider files more than these # of bytes to prune, defaults to '%(default)s'.",
                  metavar = 'SIZE'
                 )

parser.add_argument('--exclude',
                  dest    = 'excludelist',
                  type    = str,
                  default = '/lost\+found/',
                  help    = "Exclude these parts of paths (regular expression), defaults to '%(default)s'.",
                  metavar = 'RE'
                 )

parser.add_argument('dirs', nargs=argparse.REMAINDER)  # should contain all directories to parse


args = parser.parse_args()

print args

FRSIZE = 4096

# Exclude these parts of paths
if len(args.excludelist) > 0:
   excludelist = re.compile(args.excludelist)

# Debug levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
#logging.basicConfig(stream=sys.stdout, format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %H:%M:%S', filename=sys.argv[0]+'.log', level=logging.INFO)

loglevel = logging.INFO
if   args.loglevel == 'debug':
   loglevel = logging.DEBUG
elif args.loglevel == 'info':
   loglevel = logging.INFO
elif args.loglevel == 'warning':
   loglevel = logging.WARNING
elif args.loglevel == 'error':
   loglevel = logging.ERROR
elif args.loglevel == 'critical':
   loglevel = logging.CRITICAL

logging.basicConfig(stream=sys.stdout, format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %H:%M:%S', level=loglevel)

def excludeThis(fullPath):

   if excludelist.search(fullPath + '/'):
      logging.debug("Exclude: " + fullPath)
      return(True)

   return(False)


# Buiding dictionary of same files based on file size
def sameFileSize(rootdir):
   #root_to_subtract = re.compile(r'^.*?' + rootdir + r'[\\/]{0,1}')

   files_set = {}
   hLinks = 0
   found = 0
   small = 0
   large = 0
   alreadySaved = 0
   previousUpdate = time.time()

   for (dirpath, dirnames, filenames) in os.walk(rootdir):
      for filename in filenames + dirnames:
         full_path = os.path.join(dirpath, filename)

         if excludeThis(full_path): # skip if in exclude list
            continue

         if os.path.islink(full_path): # if symlink skip
            continue

         # todo check and skip hard linked files, now files will be re-linked

         #relative_path = root_to_subtract.sub('', full_path, count=1)
         statinfo = os.stat(full_path)
         #fs=os.path.getsize(full_path)
         fs = statinfo.st_size

         if ( fs == 0 ):
            logging.debug('zero byte file: '+full_path)
            continue

         total = small + large + found
         if time.time() - previousUpdate > args.updates:
            previousUpdate= time.time()
            #if (total) % 500000 == 0:
            fname = full_path.replace(rootdir, '')
            if len(fname) > 90:
               fname = fname[0:10] + '...' + fname[-90:]

            logging.info("Stat: files f=%d/s=%d/b=%d/T=%d, last file=%s" % (found, small, large, total, fname))

         if ( fs <= args.minFSize ): #skip files less than min. file size.
            small = small + 1
            continue

         if ( fs >= args.maxFSize ): #skip files more than max. file size.
            large = large + 1
            continue

         # if file and hardlink
         #if (os.stat(full_path).st_nlink > 1) and os.path.isfile(full_path):
         #   #print "HL Exclude:", full_path, os.stat(full_path).st_nlink
         #   hLinks = hLinks + 1
         #   alreadySaved = alreadySaved + fs
         #   continue

         if ( os.path.isfile(full_path) ): # build dict of list of files with same file size
            ino = statinfo.st_ino
            if fs not in files_set.keys():
               files_set[fs] = {}
            if ino not in files_set[fs].keys():
               files_set[fs][ino] = {}
               files_set[fs][ino]['files'] = []
               files_set[fs][ino]['digest'] = ''
               files_set[fs][ino]['stat'] = ''
            files_set[fs][ino]['files'].append(full_path)
            found = found + 1

            if (sys.getsizeof(files_set) > 1000000000): #don;t know if it works, but limit building a dict too large
               logging.critical("Set has "+str(len(files_set))+" elements and is larger than 1 GB, exiting")
               exit(1)

   logging.info("found " + str(found)+ " files")
   logging.info("Skipped " + str(hLinks) + " (hard-) linked files, total size "+sizeof_fmt(alreadySaved) )
   logging.info("Skipped " + str(small) + " small (<"+str(args.minFSize)+"byte) files" )
   logging.info("Skipped " + str(large) + " large (>"+str(args.maxFSize)+"byte) files" )


   return files_set


#build dict of lists of files with the same digest
def sameFileDigest(myList):

   bufSize = 118 * 1024 # 118KB seems to work fine on QNAP
   files_set = {}

   for ino in myList:
      if len(myList[ino]['files']) == 0:
         continue

      filename = myList[ino]['files'][0]
      hasher = hashlib.new(args.algorithm)

      if myList[ino]['digest'] != '':
         digest = myList[ino]['digest']
         #print "Digest calc for file %s - using cache value" % filename

      else:
         #print "Digest calc for file %s" % filename

         with open(filename, 'rb') as afile:
            for chunk in iter(lambda: afile.read(bufSize), ""):
               hasher.update(chunk)
            digest = hasher.hexdigest()
            myList[ino]['digest'] = digest

      if digest not in files_set.keys():
         files_set[digest] = {}
      if ino not in files_set[digest].keys():
         files_set[digest][ino] = []
      for file in myList[ino]['files']:
         files_set[digest][ino].append(file)

   return(files_set)

#del keys form dict that have lists with a length of 1 because these are not doubles
def delKeys(dict):
   for i in dict.keys():
      if len(dict[i]) == 1:
         del dict[i]
   return()

# do the actual deletions and (hard-)linking
def pruneList(dir, list, fsData, size):
   # list = {'7c7c06ac75e62b679b9597319dbfc114': {1581216: ['./t.102', './t.101'], 1581226: ['./t.40', './t.30', './t.3']}}
   saved = 0

   # Determine inode with most files linked to it
   biggestlist = -1
   biggestino  = -1
   for ino in list:
      if len(list[ino]) > biggestlist:
            biggestlist = len(list[ino])
            biggestino  = ino

   # We use the "biggest" inode as the reference, let's check whether it still exists
   referencefile = list[biggestino][0]
   if not os.path.isfile(referencefile):
      logging.critical("Skipping pruning for size=%s as reference file %s is not found anymore!" % (size, referencefile))
      return(saved)

   # Loop through the inodes to check on duplication:
   for ino in list:

      logging.debug("   LIST before: %s" % list[ino])

      # The inode used by most files is already fine
      if ino == biggestino:
         logging.debug("Following files are already nicely hardlinked: %s" % list[ino])
         continue

      files2remove = []
      for file in list[ino]:

         # for logging purposes, shorten the filename a bit:
         sf1 = file.replace(dir, '')
         sf2 = referencefile.replace(dir, '')
         if args.DryRun:
            logging.info("*** Dry Run *** Create hard link: %s  to file %s" % (sf1, sf2))

         else:
            logging.info("Create hard link: %s  to file  %s" % (sf1, sf2))

            # Here is the actual de-duplication, only do this when the inode still exists and the size
            # has not changed:
            #if args.debug:
            #   pdb.set_trace()
            if os.path.isfile(file):
               statinfo = os.stat(file)
               sizeNow  = statinfo.st_size
               inoNow   = statinfo.st_ino

               if (sizeNow == size)  and  (inoNow == ino):
                  os.rename(file, file + "_prune")
                  os.link(referencefile, file)
                  os.unlink(file + "_prune")
                  logging.debug("Delete: " + file)
               else:
                  logging.warning("Skipping file as it has been changed: size=%s/%s  ino=%s/%s" % (sizeNow, size, inoNow, ino))
                  continue
            else:
               logging.critical("Skipping pruning for size=%s as file %s is not found anymore!" % (size, file))
               continue

         files2remove.append(file)

      for file in files2remove:
         list[ino].remove(file)
         list[biggestino].append(file)
         fsData[size][ino]['files'].remove(file)
         fsData[size][biggestino]['files'].append(file)

      logging.debug("   files 2 remove: %s" % files2remove)
      logging.debug("   LIST after : %s" % list[ino])
      saved = saved + os.path.getsize(referencefile)

   #print "BLIST after %s" % list[biggestino]

   return(saved)

# print a nice human readable file size
def sizeof_fmt(num, suffix='B'):
   for unit in ['','K','M','G','T','P','E','Z']:
      if abs(num) < 1024.0:
         return "%3.1f %s%s" % (num, unit, suffix)
      num /= 1024.0
   return "%.1f %s%s" % (num, 'Yi', suffix)


# Main
if __name__ == '__main__':

   logging.info(' *** start run ***')

   for dir in args.dirs:

      # check blocksize on file system
      FRSIZE = os.statvfs(dir).f_frsize

      if not os.path.isdir(dir):
         logging.error("Specified directory %s does not exist" % dir)
         sys.exit("ERROR: Directory %s does not exist" % dir)

      # build dictionary of lists based on same filesize
      fsData = sameFileSize(dir)
      # lists with one file are not interesting because they are not double
      delKeys(fsData)

      logging.info('%s files in %s' % (len(fsData), dir))

      saved = 0

      if args.debug:
         print 'fsData before'
         print fsData

      fsDataCounter = 0
      fsDataLength  = len(fsData)

      # Dump data in json format
      try:
         fname = '%s/fsData-before-%s.json' % (dir, datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
         file = open(fname, 'w')
         json.dump(fsData, file, sort_keys=True, indent=2)
         file.close()
      except:
         logging.warning('Writing json file %s failed' % fname)
         pass

      for size in sorted(fsData, reverse=True):
         logging.debug("Processing files with size=%s" % size)
         fsDataCounter += 1
         logging.info("Digest calc for %3d files with size %9d bytes, step %3d out of %d" % (len(fsData[size]), size, fsDataCounter, fsDataLength) )

         for ino in fsData[size]:
               logging.debug("Processing files with size=%s and ino=%s" % (size, ino))

               #if len(fsData[i]) > 1:
               # files_set[fs][ino]['files'] = []
               # create dictionary with list of doubles based on Digest
               logging.debug("Digest calc for size " + sizeof_fmt(size) )
               logging.debug( "Size Check: " + str(len(fsData[size])) + " doubles found for size " + sizeof_fmt(int(size)) )
               hashData = sameFileDigest(fsData[size])

               # lists with one file are not interesting because they are not double
               delKeys(hashData)
               logging.debug( "Digest check : %s doubles found for size %s" % (len(hashData), sizeof_fmt(size)) )

               for digest in hashData:
                  # Here we have a list of files that could be hard-linked
                  # do the actually deletions/linking
                  saved = pruneList(dir, hashData[digest], fsData, size)

         logging.info( "Saved so far: " + sizeof_fmt(saved) )

      # Dump data in json format
      try:
         fname = '%s/fsData-after--%s.json' % (dir, datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
         file = open(fname, 'w')
         json.dump(fsData, file, sort_keys=True, indent=2)
         file.close()
      except:
         logging.error('Writing json file %s failed' % fname)
         pass

      if args.debug:
         print 'fsData after'
         print fsData

   logging.info(" *** Total Saved *** : " + sizeof_fmt(saved) )
   logging.info('end run\n')

