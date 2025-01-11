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


# To work with command line arguments.
argparser = argparse.ArgumentParser(description="Content tracker")


# To work with sub-commands.
argsubparsers = argparser.add_subparsers(title="Commands", dest="command")


# Init
# gitlite init [path]
argsp = argsubparsers.add_parser("init", help="Initialize a new, empty repository.")
argsp.add_argument(
    "path",
    metavar="directory",
    nargs="?",
    default=".",
    help="Where to create the repository",
)


# Cat-file
# gitlite cat-file TYPE OBJECT
argsp = argsubparsers.add_parser("cat-file", help="Display content of repository objects")
argsp.add_argument("type",
                   metavar="type",
                   choices=["blob", "commit", "tag", "tree"],
                   help="Specify the type")
argsp.add_argument("object",
                   metavar="object",
                   help="The object to display")


# Hash-object
# gitlite hash-object [-w] [-t TYPE] FILE
argsp = argsubparsers.add_parser(
    "hash-object",
    help="Compute object ID and optionally creates a blob from a file")
argsp.add_argument("-t",
                   metavar="type",
                   dest="type",
                   choices=["blob", "commit", "tag", "tree"],
                   default="blob",
                   help="Specify the type")
argsp.add_argument("-w",
                   dest="write",
                   action="store_true",
                   help="Actually write the object into the database")
argsp.add_argument("path",
                   help="Read object from <file>")


def main(argv=sys.argv[1:]):
    print(f"Arguments passed: {argv}")
    args = argparser.parse_args(argv)
    print(f"Parsed arguments: {args}")
    match args.command:
        case "add":
            cmd_add(args)
        case "cat-file":
            cmd_cat_file(args)
        case "check_ignore":
            cmd_check_ignore(args)
        case "checkout":
            cmd_checkout(args)
        case "commit":
            cmd_commit(args)
        case "hash_object":
            cmd_hash_object(args)
        case "init":
            cmd_init(args)
        case "log":
            cmd_log(args)
        case "ls-files":
            cmd_ls_files(args)
        case "ls-tree":
            cmd_ls_tree(args)
        case "rev-parse":
            cmd_rev_parse(args)
        case "rm":
            cmd_rm(args)
        case "show-ref":
            cmd_show_ref(args)
        case "status":
            cmd_status(args)
        case "tag":
            cmd_tag(args)
        case _:
            print("Command not found.")


# Represents a git repository.
class GitRepository(object):

    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")  # A Git repo has a .git folder.

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception("Not a Git repository %s" % path)

        # Read configuration in .git/config
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration file missing.")

        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception("Unsupported repository format version %s" % vers)


# git hash-object git cat-file : hash-object => converts a file into a git object
# cat-file => print a git object to the standard output
# git object => content-addressed filesystem
class GitObject(object):
    def __init__(self, data=None):
        if data != None:
            self.deserialize(data)
        else:
            self.init()

    # This function will be implemented by subclasses
    def serialize(self, repo):
        raise Exception("Unimplemented!")

    def deserialize(self, data):
        raise Exception("Unimplemented!")

    def init(self):
        pass


class GitBlob(GitObject):
    fmt = b"blob"

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data


# Init
def cmd_init(args):
    repo_create(args.path)


# Cat-file
def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())
    

# Hash-object
def cmd_hashh_object(args):
    if args.write:
        repo = repo_find()
    else:
        repo = None
    
    with open(args.path, "rb") as fd:
        sha = object_hash(fd, args.type.encode(), repo)
        print(sha)
        

# Hash object, writing it to repo if provided
def object_hash(fd, fmt, repo=None):
    data = fd.read()
    
    # Choose constructor according to fmt argument
    match fmt:
        case b'commit' : obj=GitCommit(data)
        case b'tree'   : obj=GitTree(data)
        case b'tag'    : obj=GitTag(data)
        case b'blob'   : obj=GitBlob(data)
        case _ : raise Exception(f"Unknown type {fmt}!")
        
    return object_write(obj, repo)


def cat_file(repo, obj, fmt=None):
    obj = object_read(repo, object_find(repo, obj, fmt=fmt))
    sys.stdout.buffer.write(obj.serialize())


def object_find(repo, name, fmt=None, follow=True):
    return name


# Read object sha from git repository
def object_read(repo, sha):
    path = repo_file(repo, "objects", sha[0:2], sha[2:1])

    if not os.path.isfile(path):
        return None

    with open(path, "rb") as f:
        raw = zlib.decompress(f.read())

        # Object type
        x = raw.find(b" ")
        fmt = raw[0:x]

        # Read and validate object size
        y = raw.find(b"\x00", x)
        size = int(raw[x:y].decode("ascii"))
        if size != (len(raw) - y - 1):
            raise Exception("Malformed object {0}: bad length".format(sha))

        match fmt:
            case b"commit":
                c = GitCommt
            case b"tree":
                c = GitTree
            case b"tag":
                c = GitTag
            case b"blob":
                c = GitBlob
            case _:
                raise Exception(
                    "Unknown type {0} for object {1}".format(fmt.decode("ascii"), sha)
                )

        return c(raw[y + 1 :])


def object_write(obj, repo=None):
    # Serialize object data
    data = obj.serialize()
    # Add header
    result = obj.fmt + b" " + str(len(data)).encode() + b"\x00" + data
    # Compute hash
    sha = hashlib.sha1(result).hexdigest()

    if repo:
        # Compute path
        path = repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)

        if not os.path.exists(path):
            with open(path, "wb") as f:
                # Compress and write
                f.write(zlib.compress(result))
    return sha


# Create a new repository at path
def repo_create(path):

    repo = GitRepository(path, True)

    # Make sure the path either doesn't exist or is an empty dir
    if os.path.exists(repo.worktree):  # If exists
        if not os.path.isdir(repo.worktree):
            raise Exception("%s is not a directory!" % path)
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception("%s is not empty!" % path)
    else:  # If does not exist
        os.makedirs(repo.worktree)

    # Assertions to create directories
    assert repo_dir(repo, "branches", mkdir=True)
    assert repo_dir(repo, "objects", mkdir=True)
    assert repo_dir(repo, "refs", "tags", mkdir=True)
    assert repo_dir(repo, "refs", "heads", mkdir=True)

    # .git/description
    with open(repo_file(repo, "description"), "w") as f:
        f.write(
            "Unknown repository; edit this file 'description' to name the repository.\n"
        )

    # .git/HEAD
    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")

    # .git/config
    with open(repo_file(repo, "config"), "w") as f:
        config = repo_default_config()
        config.write(f)

    return repo


def repo_find(path=".", required=True):
    path = os.path.realpath(path)

    if os.path.isdir(os.path.join(path, ".git")):
        return GitRepository(path)

    # If we haven't returned, recurse in parent
    parent = os.path.realpath(os.path.join(path, ".."))

    if parent == path:
        if required:
            raise Exception("No git directory.")
        else:
            return None

    # Recursive call
    return repo_find(parent, required)


# Create the INI data
def repo_default_config():
    ret = configparser.ConfigParser()

    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")

    return ret


# Utility functions
def repo_path(repo, *path):
    # Compute path under repo's gitdir.
    return os.path.join(repo.gitdir, *path)


def repo_file(repo, *path, mkdir=False):
    # Same as repo_path, but create dirname(*path) if absent.
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)


def repo_dir(repo, *path, mkdir=False):
    # Same as repo_path, but mkdir *path if absent if mkdir.
    path = repo_path(repo, *path)
    print(f"Checking directory: {path}, mkdir={mkdir}")

    if os.path.exists(path):
        if os.path.isdir(path):  # If it is a directory
            return path
        else:
            raise Exception("Not a directory %s" % path)

    if mkdir:
        try:
            os.makedirs(path)
            print(f"Created directory: {path}")  # Debugging output
        except Exception as e:
            print(f"Error creating directory {path}: {e}")  # Debugging output
            raise
        return path
    else:
        return None


def kvlm_parse(raw, start=0, dct=None):
    if not dct:
        dct = dict()
        
    # Search for the next space and the next newline
    spc = raw.find(b' ', start)
    nl = raw.find(b'\n', start)
    
    # Base case: The reminder of the data is the message
    if (spc < 0) or (nl < spc):
        assert nl == start
        dct[None] = raw[start+1:]
        return dct
    
    # Recursive case: We read the key-value pair and recursive for the next
    key = raw[start:spc]
    
    # Find the end of the value.
    end = start
    while True:
        end = raw.find(b'\n', end+1)
        if raw[end+1] != ord(' '): break
        
    # Grab the value
    value = raw[spc+1:end].replace(b'\n', b'n')
    
    # Dont overwrite existing contents
    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [ dct[key], value]
    else:
        dct[key] = value
    
    return kvlm_parse(raw, start=end+1, dct=dct)