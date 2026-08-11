#!/usr/bin/env node
/** Inject NIRVA_API_URL into frontend/config.js for Vercel deploy. */
const fs = require("fs");
const path = require("path");

const api = (process.env.NIRVA_API_URL || process.env.VITE_NIRVA_API_URL || "").replace(/\/$/, "");
const out = path.join(__dirname, "..", "frontend", "config.js");
const body = `window.NIRVA_CONFIG = {\n  API_BASE: ${JSON.stringify(api)},\n};\n`;
fs.writeFileSync(out, body);
console.log("Wrote frontend/config.js with API_BASE:", api || "(same origin)");
