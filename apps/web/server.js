// Production HTTPS custom server for Next.js.
// Reads TLS certificate from project root .cert/ directory.
// Usage: node server.js  (called via npm run start)
const { createServer } = require("https");
const { readFileSync } = require("fs");
const { parse } = require("url");
const next = require("next");
const path = require("path");

const hostname = "ai.kamoru.jk";
const port = parseInt(process.env.PORT || "3000", 10);

const app = next({ dev: false, hostname, port });
const handle = app.getRequestHandler();

// Cert files are at <repo-root>/.cert/ (two directories above apps/web/)
const certRoot = path.join(__dirname, "..", "..", ".cert");

let httpsOptions;
try {
  httpsOptions = {
    key: readFileSync(path.join(certRoot, "kamoru.jk.key")),
    cert: readFileSync(path.join(certRoot, "kamoru.jk.pem")),
  };
} catch (err) {
  console.error("[fatal] TLS certificate load failed:", err.message);
  console.error("  Expected files in:", certRoot);
  process.exit(1);
}

app
  .prepare()
  .then(() => {
    const server = createServer(httpsOptions, async (req, res) => {
      try {
        const parsedUrl = parse(req.url, true);
        await handle(req, res, parsedUrl);
      } catch (err) {
        console.error("[error] Request handling failed:", req.url, err);
        if (!res.headersSent) {
          res.statusCode = 500;
          res.end("Internal Server Error");
        }
      }
    });

    server.on("error", (err) => {
      console.error("[fatal] HTTPS server error:", err);
      process.exit(1);
    });

    server.listen(port, hostname, () => {
      console.log(`> Ready on https://${hostname}:${port}`);
    });
  })
  .catch((err) => {
    console.error("[fatal] Next.js prepare failed:", err);
    process.exit(1);
  });
