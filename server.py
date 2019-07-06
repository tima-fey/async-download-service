import os
import argparse

import asyncio
import logging
import aiofiles
from aiohttp import web
import aiohttp


try:
    import sentry_sdk
    from sentry_sdk.integrations.aiohttp import AioHttpIntegration
    from sentry_sdk.integrations.tornado import TornadoIntegration
except ImportError:
    sentry_modules = False
else:
    sentry_modules = True

try:
    with open('sentry.conf', 'r') as sentry_config_file:
        sentry_config = sentry_config_file.read()
except FileNotFoundError:
    sentry_config = None

def before_send(event, hint):
    if 'exc_info' in hint:
        _, exc_value, _ = hint['exc_info']
        if isinstance(exc_value, asyncio.CancelledError):
            return None
    return event

if sentry_config and sentry_modules:
    sentry_sdk.init(sentry_config,
                    integrations=[AioHttpIntegration(), TornadoIntegration()],
                    before_send=before_send)

parser = argparse.ArgumentParser(description='Send photos archive')
parser.add_argument('--timeout', default=0, help='Set a timeout between chunks sendind')
parser.add_argument('--dir', default='test_photos', help='Set a dir with photos ./test_photos by default')
parser.add_argument('--logging', default='enable', choices=('enable', 'disable'), help='enable/disable logging')
args = parser.parse_args()

if args.logging == 'disable':
    logging.basicConfig(level=logging.ERROR)
else:
    logging.basicConfig(level=logging.INFO)

try:
    timeout = int(args.timeout)
except ValueError:
    logging.warning('Wrong timeout. Set timeout = 0')
    timeout = 0


async def archivate(request):
    try:
        response = web.StreamResponse()
        name = request.match_info.get('archive_hash')
        if not os.path.exists('{}/{}'.format(args.dir, name)):
            raise aiohttp.web.HTTPNotFound()
        if name in ['.', '..', '']:
            raise aiohttp.web.HTTPNotFound()
        response.headers['Content-Disposition'] = 'attachment; filename="{}.zip"'.format(name)
        await response.prepare(request)
        proc = await asyncio.create_subprocess_exec(
            'zip', '-r', '-', '{}/{}'.format(args.dir, name),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        while True:
            try:
                data = await proc.stdout.readline()
                if data:
                    await asyncio.sleep(timeout)
                    await response.write(data)
                    # logging.info('Sending archive chunk ...')
                else:
                    break
            except asyncio.CancelledError:
                logging.warning('Download was interrupted')
                proc.kill()
                raise
        await response.write_eof()
        logging.info('Stop sendinf data')
        return response
    except asyncio.CancelledError:
        await proc.communicate()
        logging.warning('Download was interrupted by server')
        raise


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')

if __name__ == '__main__':
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archivate)])
    web.run_app(app)
