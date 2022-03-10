import os
import json
import asyncio
import aiofiles
import requests
from aiohttp import ClientSession
from tqdm import tqdm
from collections import namedtuple
Url = namedtuple('Url', ['url', 'params', 'data', 'cookies', 'headers'])

lmao = 'QAQ'
ua = 'NCSA_Mosaic/2.0 (Windows 3.1)'
url1 = Url('https://www.icourse163.org/web/j/courseBean.getLastLearnedMocTermDto.rpc',
            {'csrfKey':lmao}, {'termId':''}, {'NTESSTUDYSI':lmao, 'STUDY_SESS':''}, {'Content-Type':'application/x-www-form-urlencoded', 'User-Agent':ua})
url2 = Url("https://www.icourse163.org/web/j/resourceRpcBean.getResourceToken.rpc",
            {"csrfKey":lmao}, {"bizId":"", "bizType":"1", "contentType":"1"}, {"NTESSTUDYSI":lmao}, {'Content-Type':'application/x-www-form-urlencoded','User-Agent':ua})
url3 = Url("http://vod.study.163.com/eds/api/v1/vod/video", {"videoId":"", "signature":"", "clientType":"1"}, {}, {}, {'User-Agent':ua})

class Downloader:
    # https://realpython.com/async-io-python/
    def __init__(self, lst: list, workers: int) -> None:
        self.lst = list(lst)
        self.workers = workers

    async def _worker(self, queue: asyncio.Queue, session: ClientSession) -> None:
        while queue.qsize():
            url = await queue.get()
            fname = url[url.rindex('/')+1:]
            while True:
                try:
                    res = await session.get(url, headers={'User-Agent':ua})
                    f = await aiofiles.open(fname, 'wb')
                    await f.write(await res.read())
                except Exception as e:
                    print(e)
                    print('Retrying...')
                else:
                    print(f'{fname} OK')
                    break
            queue.task_done()

    async def _main(self) -> None:
        queue = asyncio.Queue()
        for i in self.lst: queue.put_nowait(i)
        tasks = []

        async with ClientSession() as session:
            for i in range(self.workers):
                task = asyncio.create_task(self._worker(queue, session))
                tasks.append(task)
            await queue.join()
            await asyncio.gather(*tasks)

    def start(self) -> None:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._main())
        #asyncio.run(self._main()) 可能出bug https://bugs.python.org/issue39232

class IcourseDownloader:
    def __init__(self, term_id: str, study_sess: str) -> None:
        self.term_id = term_id
        self.study_sess = study_sess
        self.toc = []

    def _request(self, url: Url) -> requests.Response:
        try:
            if len(url.data) > 0:
                res = requests.post(**url._asdict())
            else:
                res = requests.get(**url._asdict())
        except Exception as e:
            print(e)
            exit(1)
        return res

    # Table of Contents
    def _get_toc(self) -> list:
        fn = '%s.txt'%self.term_id
        toc = []
        if fn in os.listdir('.'):
            _toc = json.load(open(fn, 'r'))
        else:
            url1.data['termId'] = self.term_id
            url1.cookies['STUDY_SESS'] = self.study_sess
            res = self._request(url1)
            open(fn, "w").write(res.text)
            _toc = json.loads(res.text)
            res.close()

        if _toc['result'] is None:
            print("Error! Please check your input.")
            exit(1)

        _toc = _toc['result']['mocTermDto']['chapters']
        chapter_no = 0
        for chapter in _toc:
            if chapter is None or chapter['lessons'] is None: continue
            chapter_no += 1
            lesson_no = 0
            for lesson in chapter['lessons']:
                if lesson is None: continue
                lesson_no += 1
                unit_no = 0
                for unit in lesson['units']:
                    if unit is None: continue
                    unit_no += 1
                    name = "%d.%d.%d %s" % (chapter_no, lesson_no, unit_no, unit['name'])
                    video_id = str(unit['id'])
                    toc.append({'name':name, 'bizId':video_id})
        return toc

    def _parse_m3u8(self, m3u8: str) -> list:
        return [line for line in m3u8.split('\n') if line.endswith('.ts')]

    def _download_and_merge(self, url: str, name: str, lst: list) -> None:
        mp4_file = f'{name}.mp4'
        url = url[:url.rindex('/')+1]
        file_list = [url + u for u in lst]

        downloader = Downloader(file_list, 3) # 3 workers
        downloader.start()

        with open(mp4_file, 'ab') as f:
            for i in lst: 
                tmp = open(i, 'rb')
                f.write(tmp.read())
                tmp.close()
                os.remove(os.path.join(os.getcwd(),i))

        print('%s.mp4 OK' % name)

    def _download(self, video: dict) -> None:
        if os.path.exists(f'{video["name"]}.mp4'): 
            print(f'Skip {video["name"]}')
            return
        url2.data['bizId'] = video['bizId']
        res = self._request(url2)
        res = json.loads(res.text)
        if res['code'] != 0:
            print('error or `%s` isn\'t a video' % video['bizId'])
            return
        res = res['result']['videoSignDto']

        url3.params['videoId'] = res['videoId']
        url3.params['signature'] = res['signature']
        res = json.loads(self._request(url3).text)
        print('Getting the url of `%s`' % res['result']['name'])

        v = max(res['result']['videos'], key=lambda x: x['quality']) # the best quality
        url4 = Url(v['videoUrl'], {}, {}, {}, {"User-Agent":"NCSA_Mosaic/2.0 (Windows 3.1)"})
        m3u8 = self._request(url4).text
        ts_list = self._parse_m3u8(m3u8)
        self._download_and_merge(url4.url, video['name'], ts_list)

    def start(self) -> None:
        self.toc = self._get_toc()
        for video in tqdm(self.toc):
            self._download(video)
            print('')
        os.remove('%s.txt'%self.term_id)
        print('Finished.')

def main():
    term_id = input("Please input the `term_id`: ")
    study_sess = input("Please input your `STUDY_SESS`: ")
    icourse_down = IcourseDownloader(term_id, study_sess)
    icourse_down.start()

if __name__ == "__main__":
    main()
