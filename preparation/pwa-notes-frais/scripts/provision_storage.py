#!/usr/bin/env python3
"""Provisionnement Linux par descripteurs ; aucun chemin ni propriétaire configurable en CLI."""
import ctypes
import os
import stat
import sys
import time
import uuid

FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def open_directory(path):
    if not os.path.isabs(path):
        raise ValueError('Racine absolue requise')
    fd = os.open('/', FLAGS)
    try:
        for part in path.split('/'):
            if not part: continue
            if part in ('.', '..'): raise ValueError('Chemin inattendu')
            child = os.open(part, FLAGS, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def same(parent, name, fd):
    if not os.path.samestat(os.stat(name, dir_fd=parent, follow_symlinks=False), os.fstat(fd)):
        raise ValueError('Substitution documentaire')


def compliant(fd):
    s = os.fstat(fd)
    if not stat.S_ISDIR(s.st_mode) or (s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)) != (100, 101, 0o700):
        raise ValueError('Répertoire préexistant non conforme')


def rename_exclusive(parent, old, new):
    # Linux renameat2 RENAME_NOREPLACE : ne remplace jamais un répertoire préexistant.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.renameat2(parent, old.encode(), parent, new.encode(), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def provision(root='/documents', deadline=None):
    def fresh():
        if deadline is None or not deadline-60 <= time.time() < deadline:
            raise ValueError('Autorisation expirée')
    fresh()
    parent = open_directory(root)
    contracts = target = None
    try:
        p = os.fstat(parent)
        if p.st_uid != os.geteuid() or p.st_mode & 0o022:
            raise ValueError('Racine documentaire non protégée')
        contracts = os.open('contrats', FLAGS, dir_fd=parent)
        try:
            target = os.open('notes-frais', FLAGS, dir_fd=parent)
        except FileNotFoundError:
            name = '.notes-frais.provision-' + uuid.uuid4().hex
            fresh()
            os.mkdir(name, mode=0o700, dir_fd=parent)
            target = os.open(name, FLAGS, dir_fd=parent)
            same(parent, name, target)
            s = os.fstat(target)
            if s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != 0o700 or os.listdir(target):
                raise ValueError('Création incohérente')
            fresh()
            os.fchmod(target, 0o700)
            fresh()
            os.fchown(target, 100, 101)
            os.fsync(target)
            same(parent, name, target)
            same(parent, 'contrats', contracts)
            fresh()
            rename_exclusive(parent, name, 'notes-frais')
            os.fsync(parent)
        fresh()
        compliant(target)
        same(parent, 'notes-frais', target)
        same(parent, 'contrats', contracts)
        # Vérifie aussi que la racine montée désigne encore le même inode.
        check = open_directory(root)
        try:
            if not os.path.samestat(os.fstat(parent), os.fstat(check)):
                raise ValueError('Racine substituée')
        finally: os.close(check)
        fresh()
    finally:
        for fd in (target, contracts, parent):
            if fd is not None: os.close(fd)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 1: raise ValueError('Arguments interdits')
        provision(deadline=float(os.environ['WAVY_STORAGE_DEADLINE']))
    except BaseException:
        sys.exit('Provisionnement documentaire refusé ; inspection des traces requise.')
