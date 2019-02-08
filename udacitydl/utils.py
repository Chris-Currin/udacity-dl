import json
import os

import requests
from tqdm import tqdm

# Make json dump work for Python 2+3 and with Unicode
try:
    to_unicode = unicode
except NameError:
    to_unicode = str

def clean_filename(filename, replace=''):
    import unicodedata
    import string
    whitelist = "-_.() %s%s" % (string.ascii_letters, string.digits)
    char_limit = 255
    # replace spaces
    for r in replace:
        filename = filename.replace(r, '_')

    # keep only valid ascii chars
    cleaned_filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode()

    # keep only whitelisted chars
    cleaned_filename = ''.join(c for c in cleaned_filename if c in whitelist)
    if len(cleaned_filename) > char_limit:
        print(
            "Warning, filename truncated because it was over {}. Filenames may no longer be unique".format(char_limit))
    return cleaned_filename[:char_limit]


def dump_json(fname, data):
    """Write JSON file in human-readable format"""
    from multiprocessing.managers import DictProxy
    if not fname.endswith('.json'):
        fname += '.json'
    if type(data) is DictProxy:
        data = data.copy()
    str_ = json.dumps(data,
                      indent=4, sort_keys=True,
                      separators=(',', ': '), ensure_ascii=False)
    with open(fname, 'w', encoding='utf8') as outfile:
        outfile.write(to_unicode(str_))


def read_json(fname):
    """Read JSON file"""
    if not fname.endswith('.json'):
        fname += '.json'
    with open(fname) as data_file:
        return json.load(data_file)


def download_file(target_link, resource_dir, fname, force=False):
    """Download a file from `target_link` to `resource_dir`. Downloads the file in parts."""
    target_file = os.path.join(resource_dir, fname)
    r = requests.get(target_link, stream=True)
    total_size = int(r.headers.get('content-length'))
    block_size = 1024
    wrote = 0
    if os.path.exists(target_file) and not force:
        existing_file_size = os.path.getsize(target_file)
        if total_size == existing_file_size:
            print('     - Already downloaded.')
    else:
        with open(target_file, 'wb') as f:
            with tqdm(total=total_size / (32 * block_size), unit='B', unit_scale=True, unit_divisor=block_size) as pbar:
                for data in r.iter_content(32 * block_size):
                    f.write(data)
                    pbar.update(len(data))
                    wrote += len(data)
        if total_size != 0 and wrote != total_size:
            raise Exception('ERROR, something went wrong')
