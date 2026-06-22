// Genera, a partir de variables de entorno (.env), los archivos que el init de
// n8n importa al arrancar un cliente nuevo:
//   /tmp/wf.json    -> el workflow del bot con la apikey de Evolution inyectada
//   /tmp/creds.json -> las 3 credenciales (Postgres, OpenRouter header, OpenAI/OpenRouter)
//
// Los IDs de las credenciales son FIJOS y deben coincidir con los que referencia
// el workflow versionado (n8n/workflows/bot-hibrido.json), si no, los nodos
// quedarían sin credencial asignada tras el import.
const fs = require('fs');

const SEED_DIR = '/opt/n8n-seed';
const WF_SRC = `${SEED_DIR}/workflows/bot-hibrido.json`;

const env = (k) => {
  const v = process.env[k];
  if (!v || v.startsWith('__SET_')) {
    throw new Error(`Falta la variable ${k} en el .env (valor vacío o placeholder)`);
  }
  return v;
};

// --- 1) Workflow con la apikey de Evolution inyectada ---
let wf = fs.readFileSync(WF_SRC, 'utf8');
wf = wf.split('__SET_EVOLUTION_API_KEY__').join(env('EVOLUTION_API_KEY'));
fs.writeFileSync('/tmp/wf.json', wf);

// --- 2) Credenciales (formato "decrypted" que entiende `n8n import:credentials`) ---
const openrouterKey = env('OPENROUTER_API_KEY');
const creds = [
  {
    id: 'H04X1v7R4rxPQoaz',
    name: 'Postgres account 2',
    type: 'postgres',
    data: {
      // Reusamos las vars que el contenedor n8n ya tiene para su propia BD
      // (mismo Postgres del e-commerce), evitando duplicar credenciales.
      host: env('DB_POSTGRESDB_HOST'),
      database: env('DB_POSTGRESDB_DATABASE'),
      user: env('DB_POSTGRESDB_USER'),
      password: env('DB_POSTGRESDB_PASSWORD'),
      port: parseInt(process.env.DB_POSTGRESDB_PORT || '5432', 10),
      ssl: 'disable',
    },
  },
  {
    id: 'V8viWG4pBFIPsbMY',
    name: 'OpenRouter API',
    type: 'httpHeaderAuth',
    data: { name: 'Authorization', value: `Bearer ${openrouterKey}` },
  },
  {
    id: 'mKWvvXT6D2QB0INf',
    name: 'OpenAI account',
    type: 'openAiApi',
    data: { apiKey: openrouterKey, url: 'https://openrouter.ai/api/v1' },
  },
];
fs.writeFileSync('/tmp/creds.json', JSON.stringify(creds));
console.log('[seed] wf.json y creds.json generados');
