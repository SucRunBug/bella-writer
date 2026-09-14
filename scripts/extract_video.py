#!/usr/bin/env python3
"""
对标视频信息提取工具

功能：从抖音视频 URL 提取视频的标题、描述、文案字幕、互动数据和时长。
用途：在写作流程第一步，当用户提供了对标视频链接时，把对标内容抓下来，
      供后续内容诊断参考其结构、节奏和爆点。

输入：抖音视频 URL
输出：JSON（success / data / message）

注意：抖音反爬较强，抓取可能失败。失败时请改用手动方式，
      直接把视频文案粘贴给智能体即可，不要让流程卡在脚本上。

使用：
    python3 extract_video.py <抖音视频URL>
    python3 extract_video.py <抖音视频URL> -o result.json
"""

import sys
import json
import argparse
import re
import requests

try:
    from yt_dlp import YoutubeDL
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False


def extract_video_id_from_url(url: str) -> str:
    """从抖音 URL 中提取视频 ID，支持多种链接格式。"""
    patterns = [
        r'/video/(\d+)',
        r'/share/video/(\d+)',
        r'item_ids=(\d+)',
        r'aweme_id=(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_via_web(url: str) -> dict:
    """方法一：网页抓取（首选，成功率相对较高）。"""
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ),
        'Referer': 'https://www.douyin.com/',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    try:
        video_id = extract_video_id_from_url(url)
        if not video_id:
            return {'success': False, 'data': {}, 'message': '无法从 URL 中提取视频 ID'}

        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()
        html_content = response.text

        # 视频信息通常藏在 script 标签里的 __INITIAL_STATE__ 变量中
        script_pattern = r'<script>.*?window\.__INITIAL_STATE__\s*=\s*({.*?});.*?</script>'
        match = re.search(script_pattern, html_content, re.DOTALL | re.MULTILINE)

        if match:
            try:
                data = json.loads(match.group(1))
                if 'videoData' in data:
                    video_data = data['videoData']
                elif 'aweme' in data and 'detail' in data['aweme']:
                    video_data = data['aweme']['detail']
                else:
                    video_data = None

                if video_data:
                    title = video_data.get('desc', '')
                    subtitles = video_data.get('text', []) if 'text' in video_data else []
                    author_info = video_data.get('author', {})
                    statistics = video_data.get('statistics', {})
                    duration_ms = video_data.get('duration', 0)

                    result = {
                        'title': title,
                        'description': title,
                        'uploader': author_info.get('nickname', ''),
                        'uploader_id': author_info.get('uid', ''),
                        'view_count': statistics.get('play_count', 0),
                        'like_count': statistics.get('digg_count', 0),
                        'comment_count': statistics.get('comment_count', 0),
                        'share_count': statistics.get('share_count', 0),
                        'duration': duration_ms // 1000 if duration_ms else 0,
                        'tags': [],
                        'subtitles': subtitles,
                    }
                    return {'success': True, 'data': result, 'message': '提取成功（网页抓取）'}
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # 兜底：从 meta 标签提取标题和描述
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'lxml')

        desc = ''
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            desc = meta_desc.get('content', '')

        title = ''
        meta_title = soup.find('meta', attrs={'property': 'og:title'})
        if meta_title:
            title = meta_title.get('content', '')

        if desc or title:
            result = {
                'title': title or desc[:50],
                'description': desc,
                'uploader': '',
                'uploader_id': '',
                'view_count': 0,
                'like_count': 0,
                'comment_count': 0,
                'share_count': 0,
                'duration': 0,
                'tags': [],
                'subtitles': desc.split('\n') if desc else [],
            }
            return {'success': True, 'data': result, 'message': '提取成功（HTML 解析）'}

        return {'success': False, 'data': {}, 'message': '无法从网页中提取视频信息'}

    except Exception as e:
        return {'success': False, 'data': {}, 'message': f'网页抓取失败: {str(e)}'}


def extract_via_ytdlp(url: str) -> dict:
    """方法二：yt-dlp 兜底。"""
    if not YTDLP_AVAILABLE:
        return {'success': False, 'data': {}, 'message': 'yt-dlp 未安装'}

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitlesformat': 'json',
        'extract_flat': False,
        'nocheckcertificate': True,
        'user_agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ),
        'referer': 'https://www.douyin.com/',
        'ignoreerrors': True,
        'socket_timeout': 30,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return {'success': False, 'data': {}, 'message': '无法获取视频信息'}

            result = {
                'title': info.get('title') or info.get('alt_title') or '',
                'description': info.get('description') or '',
                'uploader': info.get('uploader') or info.get('channel') or '',
                'uploader_id': info.get('uploader_id') or '',
                'view_count': info.get('view_count') or 0,
                'like_count': info.get('like_count') or 0,
                'comment_count': info.get('comment_count') or 0,
                'share_count': info.get('repost_count') or 0,
                'duration': info.get('duration') or 0,
                'tags': info.get('tags') or [],
            }

            # 从描述里清出可读文案
            subtitles = []
            if result['description']:
                desc_clean = re.sub(r'#\S+', '', result['description'])
                desc_clean = re.sub(r'https?://\S+', '', desc_clean).strip()
                if desc_clean:
                    subtitles.append(desc_clean)

            # 尝试从字幕文件提取
            if info.get('subtitles'):
                for lang, sub_list in info['subtitles'].items():
                    if not sub_list:
                        continue
                    try:
                        sub_url = sub_list[0].get('url', '')
                        if not sub_url:
                            continue
                        resp = requests.get(sub_url, timeout=10, headers={
                            'User-Agent': ydl_opts['user_agent'],
                            'Referer': ydl_opts['referer'],
                        })
                        if resp.status_code == 200:
                            sub_data = resp.json()
                            if 'events' in sub_data:
                                sub_texts = []
                                for event in sub_data['events']:
                                    if 'segs' in event:
                                        text = ''.join(seg.get('utf8', '') for seg in event['segs'])
                                        if text.strip():
                                            sub_texts.append(text.strip())
                                if sub_texts:
                                    subtitles = ' '.join(sub_texts)
                                    break
                    except Exception:
                        pass
                    if subtitles and isinstance(subtitles, str):
                        break

            result['subtitles'] = subtitles
            return {'success': True, 'data': result, 'message': '提取成功（yt-dlp）'}

    except Exception as e:
        return {'success': False, 'data': {}, 'message': f'yt-dlp 提取失败: {str(e)}'}


def extract_video(url: str) -> dict:
    """主函数：依次尝试网页抓取和 yt-dlp，任一成功即返回。"""
    if not url or 'douyin.com' not in url.lower():
        return {'success': False, 'data': {}, 'message': '请提供有效的抖音视频链接'}

    result = extract_via_web(url)
    if result['success']:
        return result

    result = extract_via_ytdlp(url)
    if result['success']:
        return result

    return {
        'success': False,
        'data': {},
        'message': (
            '无法提取视频信息。抖音有访问限制，建议改用手动方式：'
            '直接复制视频文案粘贴给智能体进行分析。'
        ),
    }


def main():
    parser = argparse.ArgumentParser(description='提取对标视频信息（抖音）')
    parser.add_argument('url', help='抖音视频 URL')
    parser.add_argument('--output', '-o', help='输出文件路径（可选）', default=None)
    args = parser.parse_args()

    result = extract_video(args.url)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f'结果已保存到: {args.output}')
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
