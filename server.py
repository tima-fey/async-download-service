import os
from aiohttp import web
import aiofiles
import aiohttp
import datetime
import asyncio
import logging
import traceback
import weakref

logging.basicConfig(level=logging.INFO)

try:
    import sentry_sdk
    from sentry_sdk.integrations.aiohttp import AioHttpIntegration
    from sentry_sdk.integrations.tornado import TornadoIntegration
except ImportError:
    sentry_modules = False
else:
    sentry_modules = True
try:
    with open('sentry.conf','r') as sentry_config_file:
        sentry_config = sentry_config_file.read()
except FileNotFoundError:
    sentry_config = None

def before_send(event, hint):
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        if isinstance(exc_value, asyncio.CancelledError):
            return None
    return event

if sentry_config and sentry_modules:
    sentry_sdk.init(sentry_config,
        integrations=[AioHttpIntegration(), TornadoIntegration()],
        before_send=before_send)

async def archivate(request):
    try:
        response = web.StreamResponse()
        app['streams'].add(response)
        name = request.match_info.get('archive_hash')
        if not os.path.exists('test_photos/{}'.format(name)):
            raise aiohttp.web.HTTPNotFound()
        if name in ['.', '..', '']:
            raise aiohttp.web.HTTPNotFound()
        response.headers['Content-Disposition'] = 'attachment; filename="{}.zip"'.format(name)
        # response.force_close()
        await response.prepare(request)
        proc = await asyncio.create_subprocess_exec(
            'zip', '-r', '-', 'test_photos/{}'.format(name),
            stdout=asyncio.subprocess.PIPE)
        while True:
            try:
                data = await proc.stdout.readline()
                if data:
                    await asyncio.sleep(1)
                    await response.write(data)
                    logging.info('Sending archive chunk ...')
                else:
                    logging.info('Stop sendinf data')
                    break
            except asyncio.CancelledError:
                logging.warning('Download was interrupted')
                proc.kill()
                raise
        await response.write_eof()
        logging.info('Stop sendinf data')
        return response
    except asyncio.CancelledError:
        logging.warning('Download was interrupted by server')
        # await response.force_close()
        # await response.write_eof()
        # return response
        raise


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')

async def on_shutdown(app):
    logging.warning("on_shutdown")
    for response in app['streams']:
        # await response.write_eof()
        # await response.force_close()
        logging.warning('close')

if __name__ == '__main__':
    app = web.Application()
    app['streams'] = weakref.WeakSet()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archivate),
    ])
    app.on_shutdown.append(on_shutdown)
    web.run_app(app)
