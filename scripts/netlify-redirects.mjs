import {writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const value=process.env.BACKEND_ORIGIN;
if(!value)throw new Error('Set BACKEND_ORIGIN to the HTTPS Render service origin (no /api suffix).');
const origin=new URL(value);
if(origin.protocol!=='https:'||origin.username||origin.password||origin.pathname!=='/'||origin.search||origin.hash)throw new Error('BACKEND_ORIGIN must be an exact HTTPS origin.');
// Only the public API hostname is written. Never read or interpolate Gemini secrets.
writeFileSync(fileURLToPath(new URL('../frontend/dist/_redirects',import.meta.url)),`/api/* ${origin.origin}/api/:splat 200!\n/* /index.html 200\n`);
console.log('Generated same-origin API proxy and SPA redirects.');
