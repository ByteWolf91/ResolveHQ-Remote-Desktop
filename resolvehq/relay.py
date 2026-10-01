"""Minimal attended-session relay. For internet use, put behind TLS/reverse proxy."""
import argparse, asyncio, json, secrets, time
from .proto import send_frame, recv_frame

class Registry:
    def __init__(self, ttl=300):
        self.ttl=ttl; self.codes={}; self.attempts={}
    def issue(self, writer):
        self.expire()
        while True:
            code=f'{secrets.randbelow(1_000_000_000):09d}'
            if code not in self.codes:
                self.codes[code]=(writer,time.monotonic()+self.ttl)
                return code
    def expire(self):
        now=time.monotonic()
        for c,(w,e) in list(self.codes.items()):
            if e<=now: self.codes.pop(c,None)
    def join(self, code, ip):
        self.expire(); now=time.monotonic(); hist=[t for t in self.attempts.get(ip,[]) if now-t<60]; hist.append(now); self.attempts[ip]=hist
        if len(hist)>5: return None, 'too many attempts'
        item=self.codes.pop(''.join(x for x in code if x.isdigit()),None)
        if not item: return None,'invalid or expired code'
        return item[0],None

async def _pipe(reader, writer):
    try:
        while True:
            data=await recv_frame(reader); await send_frame(writer,data)
    except (asyncio.IncompleteReadError, ConnectionError, OSError, ValueError): pass

async def serve(host='127.0.0.1', port=7000, ttl=300):
    registry=Registry(ttl)
    async def client(r,w):
        peer=w.get_extra_info('peername'); ip=str(peer[0]) if peer else 'unknown'
        try:
            hello=json.loads(await asyncio.wait_for(recv_frame(r),10))
            if hello.get('t')=='host':
                code=registry.issue(w); await send_frame(w,json.dumps({'code':code,'ttl':ttl}).encode())
                try:
                    # Wait for the viewer to pair or code expiry / disconnect.
                    while code in registry.codes:
                        await asyncio.sleep(.1)
                        if w.is_closing(): return
                    # Host is notified by pairing event installed below.
                    event, viewer = pairs.pop(code,(None,None))
                    if not event: await send_frame(w,json.dumps({'t':'expired'}).encode()); return
                    await send_frame(w,json.dumps({'t':'paired'}).encode()); await send_frame(viewer,json.dumps({'t':'paired'}).encode())
                    await asyncio.gather(_pipe(r,viewer),_pipe(*viewer_pair[viewer]))
                finally: registry.codes.pop(code,None)
            elif hello.get('t')=='join':
                code=''.join(x for x in str(hello.get('code','')) if x.isdigit())
                hostw,err=registry.join(code,ip)
                if err: await send_frame(w,json.dumps({'t':'error','m':err}).encode()); return
                pairs[code]=(asyncio.Event(),w); viewer_pair[w]=(r,hostw)
                # host handler polls until registry entry is consumed; pair state retained separately
                pairs[code][0].set()
                # Wait for host to acknowledge; handler below's polling is avoided by notifying it.
                await asyncio.sleep(0)
                await send_frame(w,json.dumps({'t':'paired'}).encode())
                # Relay encrypted framed packets in both directions.
                await asyncio.gather(_pipe(r,host_readers[hostw]),_pipe(host_readers[hostw],w))
            else: await send_frame(w,json.dumps({'t':'error','m':'invalid request'}).encode())
        except Exception: pass
        finally:
            w.close()
            try: await w.wait_closed()
            except Exception: pass
    # Pair state uses per-code futures and host reader/writer mappings.
    pairs={}; viewer_pair={}; host_readers={}
    # Replace handler with coordinated pairing implementation.
    async def handler(r,w):
        peer=w.get_extra_info('peername'); ip=str(peer[0]) if peer else 'unknown'
        try:
            msg=json.loads(await asyncio.wait_for(recv_frame(r),10))
            if msg.get('t')=='host':
                code=registry.issue(w); fut=asyncio.get_running_loop().create_future(); pairs[code]=(fut,r,w)
                await send_frame(w,json.dumps({'code':code,'ttl':ttl}).encode())
                try: viewer_r,viewer_w=await asyncio.wait_for(fut,registry.ttl)
                except asyncio.TimeoutError:
                    registry.codes.pop(code,None); await send_frame(w,json.dumps({'t':'expired'}).encode()); return
                await send_frame(w,json.dumps({'t':'paired'}).encode()); await send_frame(viewer_w,json.dumps({'t':'paired'}).encode())
                await _pipe(r,viewer_w)
            elif msg.get('t')=='join':
                code=''.join(c for c in str(msg.get('code','')) if c.isdigit())
                hostw,err=registry.join(code,ip)
                if err: await send_frame(w,json.dumps({'t':'error','m':err}).encode()); return
                item=pairs.pop(code,None)
                if not item: await send_frame(w,json.dumps({'t':'error','m':'expired'}).encode()); return
                fut,hr,hw=item
                if not fut.done(): fut.set_result((r,w))
                await _pipe(r,hw)
            else: await send_frame(w,json.dumps({'t':'error','m':'invalid request'}).encode())
        except Exception: pass
        finally:
            w.close()
            try: await w.wait_closed()
            except Exception: pass
    srv=await asyncio.start_server(handler,host,port)
    return srv,registry

def main():
    p=argparse.ArgumentParser(); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=7000); p.add_argument('--ttl',type=int,default=300); a=p.parse_args()
    async def run():
        srv,_=await serve(a.host,a.port,a.ttl)
        print(f'ResolveHQ relay listening on {a.host}:{a.port}')
        async with srv:
            await srv.serve_forever()
    asyncio.run(run())
if __name__=='__main__': main()
