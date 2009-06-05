from paver.easy import *
from paver.path import path
from paver.setuputils import setup


setup(
    name="greenhouse",
    packages=["greenhouse"],
    version="0.1",
    author="Travis Parker",
    author_email="travis.parker@gmail.com"
)

MANIFEST = (
    "setup.py",
    "paver-minilib.zip",
)

@task
def manifest():
    path('MANIFEST.in').write_lines('include %s' % x for x in MANIFEST)

@task
@needs('generate_setup', 'minilib', 'manifest', 'setuptools.command.sdist')
def sdist():
    pass

@task
def clean():
    for p in map(path, ('greenhouse.egg-info', 'dist', 'build', 'MANIFEST.in')):
        if p.exists():
            if p.isdir():
                p.rmtree()
            else:
                p.remove()
