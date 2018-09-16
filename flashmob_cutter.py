from io import __loader__

import yaml
import json
import subprocess as sub
import sys
import os
import argparse
import pytube
from pytube import YouTube
import alignment_by_row_channels as align
import audio_offset_finder as aof
import itertools


def cmd(args):
    print('Executing command:', args)
    sub.check_call(args)


def ffmpeg(*args):
    """Execute ffmpeg process with given arguments"""
    return cmd(['ffmpeg', '-y'] + list(args))


def load_csv_city_list(path='./city_list.csv'):
    """This function parses the city list from
    http://wcs-kiel.de/international-wcs-rally-2018/
    """
    with open(path, 'r') as city_list_file:
        city_list = city_list_file.readlines()
    # first line is column headers
    keys = city_list[0][:-1].split(',')
    keys[0] = 'city'
    keys = [k.lower().replace(' ', '_') for k in keys]
    keys = ['city', 'country', 'couples', 'video_url', 'community_url']
    cities = []
    for city in city_list[1:]:
        city = city[:-1]
        fields = city.split(',')
        cities.append(dict(zip(keys, fields)))
    for city in city_list:
        city['couples'] = int(city['couples'])
    return cities


def search_youtube(cached_json=None):
    """Return a list of objects of the
    "youtube#searchResult" kind (concatenated from all the search results
    pages)
    cached_json: optional path to a previously downloaded JSON search result
        (kind: "youtube#searchListResponse")
    """
    if cached_json is not None:
        with open(cached_json, 'r') as youtube_api_response_file:
            results = json.load(youtube_api_response_file)
        results = results['items']
    else:
        # perform the YouTube search
        results = []
    # here, the results var should be a list of objects of the
    # "youtube#searchResult" kind (concatenated from all the search results
    # pages)
    return results


def load_city_list_from_youtube():
    return []


def load_city_list():
    """list of dicts:
    {city: str, country: str, couples: int, video_url: str, community_url: str}"""
    return load_csv_city_list()


def download_video(url, directory='.'):
    print('Downloading', url)
    query = {
        'res': '720p',
        'mime_type': 'video/mp4'
    }
    yt = YouTube(url)
    dash = yt.streams.filter(adaptive=True).all()
    if len(dash) == 0:
        stream_query = yt.streams.filter(progressive=True)
    else:
        stream_query = yt.streams.filter(adaptive=True)
    preferred = stream_query.filter(**query)
    if len(preferred.all()) > 0:
        stream = preferred.first()
    else:
        stream = stream_query.order_by('resolution').desc().first()
    print('Chosen stream:', stream)
    ret = stream.download(directory)
    print('YouTube download returned:', ret)


def get_cutpoints(total_seconds, chunk_seconds):
    current = 0
    cutpoints = []
    while current < total_seconds:
        cutpoints.append(current)
        current += chunk_seconds
    return cutpoints


def main():
    output_list = ""
    output_filenames = []


    split_method = 'debug'
    split_method = 'concat_config'
    split_method = 'ss'
    copy_split = False
    copy_concat = True
    chunk_seconds = 4
    cutpoints = get_cutpoints(100, chunk_seconds)
    if split_method == 'ss':
        input_files_base = [{'video_file': 'sample1.mp4', 'offset': 0}, {'video_file': 'sample2.mp4', 'offset': 5200}]
        input_files = itertools.cycle(input_files_base)
        chunk = 0
        for cut in cutpoints:
            video = next(input_files)
            input_filename = video['video_file']
            output_filename = f'{chunk:04}.mp4'
            output_list += f'file {output_filename}\n'
            output_filenames.append(output_filename)
            offset_seconds = video['offset']//1000
            millis = video['offset']%1000
            real_cut = cut + offset_seconds
            ss = f'{real_cut}.{millis}'
            # ss after
            #ffmpeg('-i', input_filename, '-acodec', 'copy', '-vcodec', 'copy', '-ss', str(cut) + '.0', '-t', str(chunk_seconds), output_filename)
            # ss before
            if copy_split:
                ffmpeg('-ss', ss, '-i', input_filename, '-acodec', 'copy', '-vcodec', 'copy', '-t', str(chunk_seconds), output_filename)
            else:
                ffmpeg('-ss', ss, '-i', input_filename, '-vf', 'fps=30', '-video_track_timescale', '18000', '-t', str(chunk_seconds), output_filename)
            chunk += 1
    elif split_method == 'concat_config':
        input_files_base = ['sample1.mp4', 'sample2.mp4']
        input_files = itertools.cycle(input_files_base)
        chunk = 0
        for cut in cutpoints:
            input_filename = next(input_files)
            output_list += f'file {input_filename}\n'
            output_list += f'inpoint {cut}.0\n'
            output_list += 'outpoint {}.0\n'.format(cut+chunk_seconds)
    elif split_method == 'debug':
        l = ['A', 'B']
        l2 = itertools.cycle(l)
        output_list = ""
        for i in range(30):
            name = next(l2) + str(i) + '.mp4'
            output_list += f'file {name}\n'
            output_filenames.append(name)

    output_list_filename = 'output_list.txt'
    with open(output_list_filename, 'w') as output_list_file:
        output_list_file.write(output_list)

    cat_method = 'concat_demuxer'
    #cat_method = 'concat_proto'

    ###################
    # concat demuxer
    ###################
    if cat_method == 'concat_demuxer':
        if copy_concat:
            ffmpeg('-f', 'concat', '-i', output_list_filename, '-c', 'copy', 'out.mp4')
        else:
            ffmpeg('-f', 'concat', '-i', output_list_filename, '-vf', 'fps=30', '-video_track_timescale', '18000', 'out.mp4')
    elif cat_method == 'concat_proto':
    ##########################
    # concat protocol (https://trac.ffmpeg.org/wiki/Concatenate#protocol)
    ##########################
    # convert to intermediate (https://trac.ffmpeg.org/wiki/Concatenate#Usingintermediatefiles)
        for out_file in output_filenames:
            ffmpeg('-i', out_file, '-c', 'copy', '-bsf:v', 'h264_mp4toannexb', '-f', 'mpegts', f'{out_file}.ts')
        intermediate_output_filenames = map(lambda s: s + '.ts', output_filenames)
        ffmpeg('-i', 'concat:' + '|'.join(intermediate_output_filenames), '-c', 'copy', 'out.mp4')
    elif cat_method == 'concat_filter':
    ###########################
    # concat filter (https://trac.ffmpeg.org/wiki/Concatenate#filter)
    ###########################
        output_filenames

    sys.exit(0)

    cities = load_city_list()
    print(json.dumps(cities, indent=4))
    for c in cities[:2]:
        if 'youtu' in c['link_to_video']:
            #download_video(c['link_to_video'])
            print(c['link_to_video'])
    #delay = aof.find_offset('sample1.mp4', 'sample2.mp4', correl_nframes=10)
    #delay = align.align('sample1.mp4', 'sample2.mp4', prefix_seconds=15, target_sample_rate=8000)
    #print(delay)
    pass


if __name__ == '__main__':
    main()
