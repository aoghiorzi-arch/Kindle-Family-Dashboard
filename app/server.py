"""Local-only demo. NOT suitable for public deployment; no authentication."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path
import json, sys
from .render import png_bytes

ROOT=Path(__file__).resolve().parent
DATA=json.loads((ROOT/'seed.json').read_text())
HTML=(ROOT/'index.html').read_text() if (ROOT/'index.html').exists() else ''
class Handler(BaseHTTPRequestHandler):
 def send(self,status,body,ctype):
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/':return self.send(200,HTML.encode(),'text/html; charset=utf-8')
  if path=='/frame.png':return self.send(200,png_bytes(DATA),'image/png')
  if path=='/api/state':return self.send(200,json.dumps(DATA).encode(),'application/json')
  return self.send(404,b'Not found','text/plain')
 def do_POST(self):
  path=urlparse(self.path).path
  if path not in ('/api/shopping','/api/events'):return self.send(404,b'Not found','text/plain')
  try:
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=4096: raise ValueError('Invalid body size')
   payload=json.loads(self.rfile.read(length))
   title=payload.get('title')
   if not isinstance(title,str) or not 1<=len(title.strip())<=100:raise ValueError('Title must be 1–100 characters')
   entry={'title':title.strip()}
   if path=='/api/shopping':entry['done']=False;DATA['shopping'].append(entry)
   else:
    when=payload.get('time','')
    if not isinstance(when,str) or len(when)>30:raise ValueError('Invalid time')
    entry.update(time=when,private=bool(payload.get('private',False)));DATA['events'].append(entry)
   return self.send(201,json.dumps({'ok':True,'item':entry}).encode(),'application/json')
  except (ValueError,TypeError,json.JSONDecodeError) as exc:
   return self.send(400,json.dumps({'error':str(exc)}).encode(),'application/json')

def main():
 port=int(sys.argv[1]) if len(sys.argv)>1 else 8765
 # Only localhost; explicitly no auth / no remote access.
 server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
 print(f'Local demo: http://127.0.0.1:{port} (Ctrl-C to stop)',flush=True)
 server.serve_forever()
if __name__=='__main__':main()
