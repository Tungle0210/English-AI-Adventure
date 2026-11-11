"""Local HTTPS reverse-proxy rehearsal, never a production server."""
import argparse,http.client,ssl,sys,json,threading,time
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path

class Proxy(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def forward(self):
        length=int(self.headers.get('Content-Length','0'))
        if length>3*1024*1024:
            self.send_error(413);return
        try:body=self.rfile.read(length) if length else None
        except OSError:return
        headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','transfer-encoding')};headers['Host']='127.0.0.1:'+str(self.server.backend_port)
        started=time.monotonic()
        connection=http.client.HTTPConnection('127.0.0.1',self.server.backend_port,timeout=26)
        try:
            connection.request(self.command,self.path,body=body,headers=headers);response=connection.getresponse();data=response.read()
            self.send_response(response.status)
            for k,v in response.getheaders():
                if k.lower() not in ('connection','transfer-encoding','content-length','server','date'):self.send_header(k,v)
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            if self.command=='PUT' and self.path.startswith('/api/uploads/'):
                with self.server.metrics_lock:
                    self.server.metrics['chunks'].append({'bytes':len(body or b''),'status':response.status,'duration_ms':round((time.monotonic()-started)*1000,2)})
                    self.server.metrics_file.write_text(json.dumps(self.server.metrics),encoding='utf-8')
        except TimeoutError:
            try:self.send_error(504,'Local proxy 26s deadline')
            except OSError:pass
        except OSError:pass # Browser refresh/abort is expected, never log cookies or payloads.
        finally:connection.close()
    do_GET=forward;do_POST=forward;do_PUT=forward;do_DELETE=forward;do_OPTIONS=forward

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8443);p.add_argument('--backend-port',type=int,default=8000);args=p.parse_args()
    # Temporary self-signed certificate stays in ignored local cache.
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime,timedelta,timezone
    folder=Path('.cache/production-tls');folder.mkdir(parents=True,exist_ok=True)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')]);now=datetime.now(timezone.utc)
    cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False).sign(key,hashes.SHA256())
    (folder/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));(folder/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Proxy);server.backend_port=args.backend_port;server.metrics_lock=threading.Lock();server.metrics={'chunks':[]};server.metrics_file=Path('reports/production/proxy-metrics.json');server.metrics_file.parent.mkdir(parents=True,exist_ok=True);server.metrics_file.write_text(json.dumps(server.metrics),encoding='utf-8')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(folder/'cert.pem',folder/'key.pem');server.socket=context.wrap_socket(server.socket,server_side=True)
    print('Local HTTPS proxy ready; per-request timeout26s.',flush=True);server.serve_forever()
