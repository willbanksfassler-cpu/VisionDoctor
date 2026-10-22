import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDirectory, "..");
const destination = path.join(
  projectRoot,
  "src",
  "vision_doctor",
  "ui",
  "theme.css",
);

const css = String.raw`
:root {
  --vd-ink: #10233f;
  --vd-muted: #63738a;
  --vd-primary: #2563eb;
  --vd-primary-deep: #1746b5;
  --vd-accent: #0f9d8a;
  --vd-accent-soft: #e7f8f4;
  --vd-border: #dbe5f1;
  --vd-border-strong: #c8d7e8;
  --vd-surface: rgba(255, 255, 255, 0.96);
  --vd-shadow: 0 14px 40px rgba(29, 52, 86, 0.08);
}

.stApp {
  background:
    radial-gradient(circle at 3% 0%, rgba(37, 99, 235, 0.10), transparent 31rem),
    radial-gradient(circle at 98% 16%, rgba(15, 157, 138, 0.08), transparent 25rem),
    linear-gradient(180deg, #f8fbff 0%, #f4f8fc 52%, #eef4f9 100%);
  color: var(--vd-ink);
  font-family: Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}

.block-container {
  max-width: 1220px;
  padding-top: 1.35rem;
  padding-bottom: 4.5rem;
}

h1, h2, h3, h4 {
  color: var(--vd-ink);
  letter-spacing: -0.025em;
}

h3 {
  margin-top: 1.35rem;
  margin-bottom: 0.35rem;
  font-size: 1.35rem;
}

.vd-hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 250px;
  gap: 2.4rem;
  overflow: hidden;
  margin-bottom: 1.25rem;
  padding: 2.25rem 2.45rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 26px;
  background:
    linear-gradient(120deg, rgba(15, 157, 138, 0.14), transparent 38%),
    linear-gradient(135deg, #10233f 0%, #183d75 66%, #165b72 100%);
  box-shadow: 0 22px 60px rgba(16, 35, 63, 0.22);
  color: #ffffff;
}

.vd-hero::after {
  position: absolute;
  right: -5rem;
  bottom: -9rem;
  width: 24rem;
  height: 24rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 50%;
  box-shadow:
    0 0 0 3rem rgba(255, 255, 255, 0.025),
    0 0 0 6rem rgba(255, 255, 255, 0.018);
  content: "";
}

.vd-hero__content,
.vd-hero__summary {
  position: relative;
  z-index: 1;
}

.vd-eyebrow {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  margin-bottom: 1rem;
  color: #a9c8ff;
  font-size: 0.72rem;
  font-weight: 750;
  letter-spacing: 0.14em;
}

.vd-eyebrow span {
  width: 0.52rem;
  height: 0.52rem;
  border-radius: 50%;
  background: #42ddc5;
  box-shadow: 0 0 0 5px rgba(66, 221, 197, 0.13);
}

.vd-hero h1 {
  margin: 0;
  color: #ffffff;
  font-size: clamp(2rem, 4vw, 3.35rem);
  line-height: 1.13;
  letter-spacing: -0.045em;
}

.vd-hero h1 em {
  color: #7ce6d7;
  font-style: normal;
}

.vd-hero p {
  max-width: 690px;
  margin: 1rem 0 1.2rem;
  color: #d3e0f3;
  font-size: 1rem;
  line-height: 1.75;
}

.vd-hero__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.vd-hero__tags span {
  padding: 0.38rem 0.68rem;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.075);
  color: #e8f0fb;
  font-size: 0.78rem;
}

.vd-hero__summary {
  align-self: center;
  padding: 1.25rem;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.075);
  backdrop-filter: blur(8px);
}

.vd-hero__summary span,
.vd-hero__summary small {
  display: block;
}

.vd-hero__index {
  margin-bottom: 1.7rem;
  color: #7ce6d7;
  font-size: 0.78rem;
  font-weight: 750;
  letter-spacing: 0.12em;
}

.vd-hero__summary strong {
  display: block;
  margin-bottom: 0.45rem;
  font-size: 1.08rem;
}

.vd-hero__summary small {
  color: #bfd0e8;
  line-height: 1.55;
}

[data-testid="stCaptionContainer"] {
  color: var(--vd-muted);
}

[data-testid="stMetric"] {
  position: relative;
  overflow: hidden;
  min-height: 112px;
  padding: 1.05rem 1.15rem;
  border: 1px solid var(--vd-border);
  border-radius: 18px;
  background: var(--vd-surface);
  box-shadow: var(--vd-shadow);
}

[data-testid="stMetric"]::before {
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: linear-gradient(180deg, var(--vd-primary), var(--vd-accent));
  content: "";
}

[data-testid="stMetricValue"] {
  color: var(--vd-primary-deep);
  font-weight: 760;
  letter-spacing: -0.035em;
}

[data-baseweb="tab-list"] {
  gap: 0.42rem;
  padding: 0.42rem;
  border: 1px solid var(--vd-border);
  border-radius: 17px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 8px 28px rgba(29, 52, 86, 0.06);
  backdrop-filter: blur(12px);
}

[data-baseweb="tab"] {
  min-height: 48px;
  padding-inline: 1.15rem;
  border-radius: 12px;
  color: #53647c;
  font-weight: 650;
  transition: color 160ms ease, background 160ms ease, box-shadow 160ms ease;
}

[aria-selected="true"][data-baseweb="tab"] {
  background: linear-gradient(135deg, #edf3ff, #e8f8f5);
  color: var(--vd-primary-deep);
  box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.12);
}

[data-baseweb="tab-highlight"] {
  background-color: var(--vd-primary);
}

[data-testid="stFileUploader"] {
  padding: 0.35rem;
  border-radius: 20px;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.04), rgba(15, 157, 138, 0.05));
}

[data-testid="stFileUploaderDropzone"] {
  min-height: 150px;
  border: 1.5px dashed #9bb5d5;
  border-radius: 17px;
  background: rgba(255, 255, 255, 0.88);
}

[data-testid="stFileUploaderDropzone"] button {
  border-color: var(--vd-primary);
  color: var(--vd-primary-deep);
}

[data-testid="stExpander"],
[data-testid="stDataFrame"] {
  border: 1px solid var(--vd-border);
  border-radius: 16px;
  background: var(--vd-surface);
  box-shadow: 0 8px 26px rgba(29, 52, 86, 0.045);
}

[data-testid="stExpander"] details summary {
  padding-block: 0.2rem;
  font-weight: 620;
}

[data-baseweb="select"] > div,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {
  border-color: var(--vd-border-strong);
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.95);
}

.stButton > button,
.stDownloadButton > button {
  min-height: 46px;
  border-radius: 12px;
  font-weight: 700;
  letter-spacing: 0.01em;
  transition: transform 150ms ease, box-shadow 150ms ease, border-color 150ms ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
  transform: translateY(-1px);
}

.stButton > button[kind="primary"] {
  border-color: transparent;
  background: linear-gradient(135deg, var(--vd-primary), #1c79d8);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.24);
  color: #ffffff;
}

.stButton > button[kind="primary"]:hover {
  border-color: transparent;
  box-shadow: 0 13px 30px rgba(37, 99, 235, 0.30);
}

.stButton > button:disabled {
  transform: none;
  box-shadow: none;
}

.stDownloadButton > button {
  border: 1px solid #86cfc3;
  background: linear-gradient(135deg, #ffffff, var(--vd-accent-soft));
  color: #087668;
}

.stDownloadButton > button:hover {
  border-color: var(--vd-accent);
  box-shadow: 0 10px 24px rgba(15, 157, 138, 0.14);
}

.stAlert {
  border-radius: 14px;
  border-width: 1px;
}

[data-testid="stImage"] img {
  border: 1px solid var(--vd-border);
  border-radius: 14px;
  box-shadow: 0 8px 22px rgba(29, 52, 86, 0.08);
}

hr {
  border-color: var(--vd-border);
}

@media (max-width: 720px) {
  .block-container {
    padding: 0.75rem 0.78rem 3rem;
  }

  .vd-hero {
    grid-template-columns: 1fr;
    gap: 1.1rem;
    padding: 1.45rem 1.25rem;
    border-radius: 20px;
  }

  .vd-hero h1 {
    font-size: 2rem;
  }

  .vd-hero p {
    font-size: 0.92rem;
  }

  .vd-hero__summary {
    display: none;
  }

  .vd-hero__tags span {
    font-size: 0.72rem;
  }

  [data-baseweb="tab-list"] {
    overflow-x: auto;
    justify-content: flex-start;
    flex-wrap: nowrap;
  }

  [data-baseweb="tab"] {
    min-width: max-content;
    padding-inline: 0.8rem;
    font-size: 0.82rem;
  }

  [data-testid="stMetric"] {
    min-height: 96px;
  }

  .stButton > button,
  .stDownloadButton > button {
    min-height: 48px;
  }
}
`.trimStart();

const normalized = `${css.trimEnd()}\n`;
if (process.argv.includes("--check")) {
  const current = fs.readFileSync(destination, "utf8").replaceAll("\r\n", "\n");
  if (current !== normalized) {
    console.error("theme.css 与 Node.js 生成结果不一致");
    process.exitCode = 1;
  } else {
    console.log("theme.css 校验通过");
  }
} else {
  fs.writeFileSync(destination, normalized, "utf8");
  console.log(`已生成 ${destination}`);
}
