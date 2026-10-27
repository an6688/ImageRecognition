"""Serve one AstroTrack report locally, with reviewed-file moves confined to its image folder."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import sys
import webbrowser
from urllib.parse import urlsplit
from organize_review import organize_document, plan_moves

SESSION_TAG = '<script id="local-session" type="application/json">null</script>'
DATA_TAG = '<script id="report-data" type="application/json">'
MAX_REQUEST = 4 * 1024 * 1024


class ReviewServer(HTTPServer):
    def __init__(self, report, source_dir, port=8765):
        self.report = Path(report).resolve(strict=True)
        self.root = Path(source_dir).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('Image folder must be a directory.')
        self.html = self.report.read_text(encoding='utf-8')
        if SESSION_TAG not in self.html:
            raise ValueError('Regenerate this report with the current report.py first.')
        data = json.loads(self.html.split(DATA_TAG,1)[1].split('</script>',1)[0])
        self.allowed = {str(Path(f['path']).absolute()) for f in data['frames']}
        if not self.allowed or any(not Path(p).is_relative_to(self.root) for p in self.allowed):
            raise ValueError('Every report image must belong to the selected image folder.')
        self.token = secrets.token_urlsafe(32)
        self.plans = {}
        self.moved = {}
        super().__init__(('127.0.0.1',port), Handler)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.refresh_moved()

    def refresh_moved(self):
        """Only report completed moves with an existing destination and absent source."""
        self.moved = {}
        rejected = self.root/'Rejected'
        if not rejected.exists() or rejected.resolve() != rejected:
            return
        for journal in rejected.glob('astro-moves-*.jsonl'):
            if journal.is_symlink():
                continue
            try:
                for line in journal.read_text(encoding='utf-8').splitlines():
                    try:
                        entry=json.loads(line)
                        source=Path(entry['source'])
                        destination=rejected/source.relative_to(self.root)
                        if (entry.get('status')=='moved' and str(source) in self.allowed
                                and str(destination)==entry.get('destination')
                                and not source.exists() and destination.is_file()
                                and destination.resolve()==destination):
                            self.moved[str(source)]=str(destination)
                    except (ValueError,KeyError,TypeError):
                        continue
            except OSError:
                continue

    def document(self, paths):
        if not isinstance(paths,list) or not paths or len(paths)!=len(set(paths)):
            raise ValueError('Select at least one unique rejected image.')
        if any(not isinstance(p,str) or p not in self.allowed for p in paths):
            raise ValueError('A selected file does not belong to this report.')
        return {'kind':'astrotrack-rejections','schema_version':1,
                'assessments':[{'path':p,'review_decision':'reject'} for p in paths]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def respond(self, status, body, content_type='application/json'):
        if isinstance(body,dict):
            body=json.dumps(body).encode('utf-8')
        if isinstance(body,str):
            body=body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.end_headers()
        self.wfile.write(body)

    def local_host(self):
        return self.headers.get('Host')==urlsplit(self.server.origin).netloc

    def do_GET(self):
        if not self.local_host():
            return self.respond(403,{'error':'Invalid host.'})
        if self.path!='/':
            return self.respond(404,{'error':'Not found.'})
        self.server.refresh_moved()
        session={'token':self.server.token,'destination':str(self.server.root/'Rejected'),
                 'moved':self.server.moved}
        tag='<script id="local-session" type="application/json">'+json.dumps(session).replace('<','\\u003c')+'</script>'
        self.respond(200,self.server.html.replace(SESSION_TAG,tag,1),'text/html; charset=utf-8')

    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<1 or size>MAX_REQUEST:
                return self.respond(400,{'error':'Invalid request.'})
            # Consume a bounded request before replying. Closing with unread bytes
            # can reset the connection on Windows and hide an otherwise valid 403.
            self.connection.settimeout(10)
            raw=self.rfile.read(size)
            if (not self.local_host() or self.headers.get('Origin')!=self.server.origin
                    or not secrets.compare_digest(self.headers.get('X-Astro-Token',''),self.server.token)):
                return self.respond(403,{'error':'Open the report through its local launcher.'})
            if self.headers.get_content_type()!='application/json':
                return self.respond(400,{'error':'Invalid request.'})
            body=json.loads(raw)
            if self.path=='/api/plan':
                document=self.server.document(body.get('paths'))
                _,moves=plan_moves(document,self.server.root)
                key=secrets.token_urlsafe(24)
                # One reviewable plan at a time; applying consumes the plan.
                self.server.plans={key:(document,[(str(s),signature) for s,_,signature in moves])}
                return self.respond(200,{'plan':key,'destination':str(self.server.root/'Rejected'),
                    'files':[{'source':str(s),'destination':str(d)} for s,d,_ in moves]})
            if self.path=='/api/move':
                pending=self.server.plans.pop(body.get('plan'),None)
                if pending is None:
                    raise ValueError('Preview these moves again before applying.')
                document,signatures=pending
                _,moves=plan_moves(document,self.server.root)
                if signatures!=[(str(s),signature) for s,_,signature in moves]:
                    raise ValueError('An image changed after the preview; no files moved.')
                journal=organize_document(document,self.server.root,True)
                self.server.refresh_moved()
                return self.respond(200,{'moved':self.server.moved,'journal':str(journal)})
            self.respond(404,{'error':'Not found.'})
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
            self.server.refresh_moved()
            self.respond(400,{'error':str(exc),'moved':self.server.moved})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('image_folder',type=Path)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    try:
        server=ReviewServer(args.report,args.image_folder,args.port)
    except (OSError,ValueError,KeyError,IndexError) as exc:
        print('review_server: '+str(exc),file=sys.stderr)
        return 2
    print('AstroTrack: '+server.origin,flush=True)
    print('Leave this window running while reviewing. Ctrl+C stops the local app.',flush=True)
    if not args.no_browser:
        webbrowser.open(server.origin)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
