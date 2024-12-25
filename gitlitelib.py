import argparse
import collections
import configparser
from datetime import datetime
import grp, pwd
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib

# To work with command line arguments
argparser = argparse.ArgumentParser(description="Content tracker")

# To work with sub-commands
argsybparsers = argparser.add_subparsers(title="Commands", dest="command")