from __future__ import print_function

import argparse

from coursedl import UdacityCourseDownloader
from nanodegreedl import UdacityNanodegreeDownloader


def main():
    # parse the commandline args
    parser = argparse.ArgumentParser(description='Download Udacity.com course videos/docs for offline use.')
    parser.add_argument('-d', dest='dest_dir', type=str, default=".",
                        help='destination directory where everything will be saved')
    parser.add_argument('course_codes', nargs="+", metavar='<course name>',
                        type=str, help='one or more course codes (from the url)')
    args = parser.parse_args()

    # download the content
    d = UdacityCourseDownloader()
    nd = None
    for cn in args.course_codes:
        if cn.startswith('nd'):
            if nd is None:
                nd = UdacityNanodegreeDownloader()
            nd.download_nanodegree(cn, dest_dir=args.dest_dir)
        else:
            d.download_course(cn, dest_dir=args.dest_dir)
    print(' Download Complete.')


if __name__ == '__main__':
    main()
