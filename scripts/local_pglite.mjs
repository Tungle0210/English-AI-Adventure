import {PGlite} from '../.cache/pg-rehearsal/node_modules/@electric-sql/pglite/dist/index.js';
import {PGLiteSocketServer} from '../.cache/pg-rehearsal/node_modules/@electric-sql/pglite-socket/dist/index.js';
const db=await PGlite.create(process.argv[2]||'.cache/pg-rehearsal/data');
const server=new PGLiteSocketServer({db,host:'127.0.0.1',port:55432,inspect:false,maxConnections:1});
await server.start();console.log('Local PostgreSQL WASM rehearsal ready, no production connection.');
process.on('SIGINT',async()=>{await server.stop();await db.close();process.exit(0)});
