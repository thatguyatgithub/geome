#!/usr/bin/python3
import argparse
import logging
import os
import shutil
import subprocess
import sys
from geopy.geocoders import Nominatim
from pathlib import Path

""" Geo locate videos and images using Exif information and sort them up """


FILENAME_CHOICES = ("date",
                    "date+location",
                   )

GEODATA_KEYWORDS = ('country',
                    'state',
                    'state_district',
                    'city',
                    'town',
                    'suburb',
                   )


class NoGPSDataException(Exception):
    pass

def parse_commandline():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('root', type=str, help="Root where to start geolocating from")
    parser.add_argument('--destination', type=str, required=True, help="Path where to reallocate videos and images after getting located")
    parser.add_argument('--format', default="date", choices=FILENAME_CHOICES, help="What information to use for renaming the file")
    parser.add_argument('--pattern', type=str, default="**/*", help="File discovery pattern")
    options = parser.parse_args()

    return options


def get_exif_from_file(file):
    metadata = {}
    try:
        raw = subprocess.check_output('exiftool -c "%.8f" {}'.format(file), shell=True).decode('utf-8').splitlines()
    except subprocess.CalledProcessError:
        raise NoGPSDataException("exif failed to grab metadata")

    for x in raw:
        _ = x.split(':', 1)
        key =_[0].strip()
        metadata[key] = _[1][1:]

    return metadata


def create_geo_folder(root, *kargs):
    path = Path(root, '/'.join(kargs[0]))
    path.mkdir(parents=True, exist_ok=True)

    return path


def get_signed_coordinate_element(element):
    element = element.split()
    if element[1] in ('S', 'W'):
        return '-{}'.format(element[0])

    return element[0]


def get_geodata_from_geolocator(location):
    geodata = []
    for geo_key in GEODATA_KEYWORDS:
        try:
            geodata.append(location[geo_key])
        except:
            pass

    return geodata

def get_geodata_from_gps_cordinates(latitude, longitude):
    geolocator = Nominatim(timeout=60)
    coordinates = '{}, {}'.format(latitude, longitude)
    logging.debug("Querying locator(%s) %s %s", geolocator.scheme, geolocator.domain, coordinates)
    raw = geolocator.reverse(coordinates).raw
    location = raw['address']
    logging.debug(location)

    return get_geodata_from_geolocator(location)


def get_geodata_from_exif(exif):
    try:
        latitude = get_signed_coordinate_element(exif['GPS Latitude'])
        longitude = get_signed_coordinate_element(exif['GPS Longitude'])
    except KeyError:
        raise NoGPSDataException("No valids GPS stored but some extif is present. Should check this")

    if '0.00000000' in (latitude, longitude):
        raise NoGPSDataException("No valid GPS stored (no fix, really?)")

    return get_geodata_from_gps_cordinates(latitude, longitude)


def get_filename_from_exif(exif, format, geodata):
    filename = ''
    extension = exif['File Type Extension']

    geodata = ' '.join(geodata)

    try:
        str_date = exif['Media Create Date']
    except KeyError:
        str_date = exif['Create Date']
    formatted_date = str_date.replace(":", "_")

    if 'date' in format:
        filename += formatted_date

    if 'location' in format:
        filename += geodata

    return Path('{}.{}'.format(filename, extension))


def reallocate_original_file_to_destination(origin, path, filename):
    new_file_path = path / filename

    if new_file_path.exists():
        if origin.stat().st_size == new_file_path.stat().st_size:
            logging.error("%s seems to be already geotagged. Safe to be removed (size=%s)", origin, new_file_path.stat().st_size)
        else:
            logging.error("Uhm, %s seems not to be %s. Check it up!", origin, new_file_path)

    else:
        shutil.move(origin, new_file_path)


def geolocate(file, destination, format):
    logging.info("Processing %s", file)
    try:
        exif = get_exif_from_file(file)
        geodata = get_geodata_from_exif(exif)
    except NoGPSDataException as e:
        logging.error("Geotagging not possible for file %s (%s)", file, e)
        return

    path = create_geo_folder(destination, geodata)
    filename = get_filename_from_exif(exif, format, geodata)

    reallocate_original_file_to_destination(file, path, filename)


def main():
    options = parse_commandline()

    search_on_root = Path(options.root).glob(options.pattern)
    for file in search_on_root:
        if file.is_dir():
            continue

        try:
            if file.relative_to(Path(options.destination)):
                logging.error("Processing files already at destination, this seems really wrong!\n(Is destination in the same path where discovery files from?)")

        except ValueError:
            geolocate(file, options.destination, options.format)

if __name__ == "__main__":
    main()
