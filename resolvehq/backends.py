"""Screen capture and attended remote input backends."""
import io
from PIL import Image
class MssCapture:
    def __init__(self, monitor=1, quality=55, max_width=1280):
        import mss
        self.sct=mss.mss(); self.monitor=monitor; self.quality=quality; self.max_width=max_width
    def grab(self):
        monitors=self.sct.monitors
        mon=monitors[self.monitor] if self.monitor < len(monitors) else monitors[0]
        shot=self.sct.grab(mon); img=Image.frombytes('RGB',shot.size,shot.rgb)
        if img.width>self.max_width: img.thumbnail((self.max_width, self.max_width*10_000))
        out=io.BytesIO(); img.save(out,format='JPEG',quality=self.quality,optimize=True); return out.getvalue()
class PynputInput:
    def __init__(self):
        from pynput.mouse import Controller as Mouse, Button
        from pynput.keyboard import Controller as Keyboard, Key
        self.mouse_ctl=Mouse(); self.keyboard_ctl=Keyboard(); self.Button=Button; self.Key=Key
        from mss import mss
        with mss() as s: self.width=s.monitors[1]['width']; self.height=s.monitors[1]['height']
    def mouse(self,x,y,action,button=None):
        from pynput.mouse import Button
        self.mouse_ctl.position=(int(x*self.width),int(y*self.height))
        b=getattr(Button,button) if button in ('left','right','middle') else None
        if action=='down' and b: self.mouse_ctl.press(b)
        elif action=='up' and b: self.mouse_ctl.release(b)
    def key(self,key,down):
        from pynput.keyboard import Key
        k=getattr(Key,key,None) or (key if len(key)==1 else None)
        if k is not None:
            (self.keyboard_ctl.press if down else self.keyboard_ctl.release)(k)
class SyntheticCapture:
    def grab(self):
        out=io.BytesIO(); Image.new('RGB',(320,200),(35,75,130)).save(out,'JPEG'); return out.getvalue()
class RecordingInput:
    def __init__(self): self.events=[]
    def mouse(self,*args): self.events.append(('mouse',*args))
    def key(self,*args): self.events.append(('key',*args))
