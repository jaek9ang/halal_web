import { useEffect, useMemo, useRef, useState } from "react";
import {
  createOcrJob,
  deleteOcrJobs,
  getInboxOcrTargets,
  getLhlnRecords,
  getMailLogs,
  getMailTargets,
  getOcrJob,
  getOcrJobs,
  uploadOcrManualFiles,
} from "../api";
import EllipsisText from "../components/EllipsisText";
import PageHeader from "../components/PageHeader";
import StatLine from "../components/StatLine";
import { formatOcrTableDate } from "../lib/format";
import { getEffectiveOcrStatus } from "../lib/ocrStatus";

function OcrPage({ setActive }) {
  const [files, setFiles] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [ocrTargets, setOcrTargets] = useState([]);
  const [mailTargets, setMailTargets] = useState([]);
  const [mailLogs, setMailLogs] = useState([]);
  const [lhlnRecords, setLhlnRecords] = useState([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [selectedJob, setSelectedJob] = useState(null);
  
  const [ocrLang, setOcrLang] = useState("eng");
  const [ocrScannedPages, setOcrScannedPages] = useState(true);
  const [ocrHistoryStatusFilter, setOcrHistoryStatusFilter] = useState("");
  const [ocrHistoryOrgFilter, setOcrHistoryOrgFilter] = useState("");
  const [ocrHistoryKeyword, setOcrHistoryKeyword] = useState("");
  const [loading, setLoading] = useState(false);
  const [fileKeyword, setFileKeyword] = useState("");
  const [checkedOcrFilePaths, setCheckedOcrFilePaths] = useState([]);
  const [checkedOcrJobIds, setCheckedOcrJobIds] = useState([]);
  const [manualUploadFiles, setManualUploadFiles] = useState([]);
  const [manualUploadOpen, setManualUploadOpen] = useState(false);
  const [ocrResultOpen, setOcrResultOpen] = useState(false);
  const [manualDragActive, setManualDragActive] = useState(false);
  const manualUploadInputRef = useRef(null);

  const candidateListRef = useRef(null);
  const jobListRef = useRef(null);
  const certificateRule =
    selectedJob?.certificate_rule ||
    selectedJob?.result?.certificate_rule ||
    selectedJob?.result?.field_guess?.certificate_rule ||
    null;

  function safeText(value) {
    const text = String(value ?? "").trim();

    if (!text) return "";
    if (text === "-") return "";
    if (text.toLowerCase() === "nan") return "";
    if (text.toLowerCase() === "none") return "";
    if (text.toLowerCase() === "null") return "";

    return text;
  }

  function parseJsonArray(value) {
    try {
      if (!value) return [];
      if (Array.isArray(value)) return value;

      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function normalizePath(value) {
    return String(value || "")
      .replaceAll("\\", "/")
      .toLowerCase()
      .trim();
  }

  function formatBytes(value) {
    const n = Number(value || 0);

    if (!n) return "-";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;

    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  }

  function pickFirst(obj, keys) {
    if (!obj) return "";

    for (const key of keys) {
      const value = safeText(obj[key]);

      if (value) return value;
    }

    return "";
  }

  function extractExpectedInfoFromMailText(text) {
    const raw = String(text || "")
      .replace(/&nbsp;/gi, " ")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>/gi, "\n")
      .replace(/<[^>]+>/g, " ")
      .replace(/\r/g, "\n")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();

    const info = {
      supplier: "",
      koreanName: "",
      englishName: "",
      maker: "",
      org: "",
      certNo: "",
      expiry: "",
      country: "",
    };

    function cleanValue(value) {
      return String(value || "")
        .replace(/^[\s:\-]+/, "")
        .replace(/[\s]+$/g, "")
        .replace(/^\[/, "")
        .replace(/\]$/, "")
        .trim();
    }

    const supplierMatch =
      raw.match(/귀사\s*\[([^\]]+)\]/) ||
      raw.match(/귀사\s+(.+?)에서/) ||
      raw.match(/업체명\s*[:：]\s*(.+?)(?:\n|$)/) ||
      raw.match(/공급사\s*[:：]\s*(.+?)(?:\n|$)/);

    if (supplierMatch) {
      info.supplier = cleanValue(supplierMatch[1]);
    }

    const itemBlockMatch = raw.match(/★★★\s*해당\s*품목\s*★★★([\s\S]*?)(?:={10,}|■■■|관리번호:|$)/);
    const itemBlock = itemBlockMatch ? itemBlockMatch[1] : raw;

    const numberedItemMatch = itemBlock.match(/(?:^|\n)\s*1\.\s*([^\n\r]+)/);
    if (numberedItemMatch) {
      info.koreanName = cleanValue(numberedItemMatch[1]);
    }

    const materialMatch =
      itemBlock.match(/원료명\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/품목명\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/제품명\s*[:：]\s*(.+?)(?:\n|$)/);

    if (!info.koreanName && materialMatch) {
      info.koreanName = cleanValue(materialMatch[1]);
    }

    const englishMatch =
      itemBlock.match(/영문명\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/english\s*name\s*[:：]\s*(.+?)(?:\n|$)/i);

    if (englishMatch) {
      info.englishName = cleanValue(englishMatch[1]);
    }

    const makerMatch =
      itemBlock.match(/제조사\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/manufacturer\s*[:：]\s*(.+?)(?:\n|$)/i);

    if (makerMatch) {
      info.maker = cleanValue(makerMatch[1]);
    }

    const countryMatch =
      itemBlock.match(/제조국\s*[:：]\s*(.+?)(?:\n|$)/) ||
      itemBlock.match(/country\s*[:：]\s*(.+?)(?:\n|$)/i);

    if (countryMatch) {
      info.country = cleanValue(countryMatch[1]);
    }

    const orgMatch =
      itemBlock.match(/인증기관\s*[:：]\s*(BPJPH|MUI|KMF|JAKIM|CICOT|IFANCA|HQC|HCA|ISA|LHLN)/i) ||
      raw.match(/\b(BPJPH|MUI|KMF|JAKIM|CICOT|IFANCA|HQC|HCA|ISA|LHLN)\b/i);

    if (orgMatch) {
      info.org = orgMatch[1].toUpperCase();
    }

    const certNoMatch =
      itemBlock.match(/인증번호\s*[:：]\s*([A-Z0-9\-_.\/]+)/i) ||
      raw.match(/certificate\s*(?:no|number)\s*[:：]?\s*([A-Z0-9\-_.\/]+)/i);

    if (certNoMatch) {
      info.certNo = cleanValue(certNoMatch[1]);
    }

    const expiryMatch =
      itemBlock.match(/유효기간\s*[:：]\s*(20\d{2}[.\-\/]\d{1,2}[.\-\/]\d{1,2})/) ||
      itemBlock.match(/만료\s*[:：]?\s*(20\d{2}[.\-\/]\d{1,2}[.\-\/]\d{1,2})/) ||
      raw.match(/valid\s*(?:until|through)?\s*[:：]?\s*(20\d{2}[.\-\/]\d{1,2}[.\-\/]\d{1,2})/i);

    if (expiryMatch) {
      info.expiry = cleanValue(expiryMatch[1]).replaceAll(".", "-").replaceAll("/", "-");
    }

    return info;
  }

  function inferOrgCandidates(...texts) {
    const joined = texts
      .map((x) => String(x || ""))
      .join(" ")
      .toUpperCase();

    const orgs = [
      "BPJPH",
      "MUI",
      "KMF",
      "JAKIM",
      "CICOT",
      "IFANCA",
      "HQC",
      "HCA",
      "ISA",
      "LHLN",
    ];

    const result = [];

    for (const org of orgs) {
      if (joined.includes(org) && !result.includes(org)) {
        result.push(org);
      }
    }

    return result;
  }

  function toIsoDate(year, month, day) {
    const y = Number(year);
    const m = Number(month);
    const d = Number(day);

    if (!y || !m || !d) return "";
    if (y < 2000 || y > 2100) return "";
    if (m < 1 || m > 12) return "";
    if (d < 1 || d > 31) return "";

    return `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }

  function extractDateCandidates(rawText, source = "ocr") {
    const text = String(rawText || "")
      .replace(/&nbsp;/gi, " ")
      .replace(/\r/g, "\n")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();

    const low = text.toLowerCase();

    const monthMap = {
      jan: 1,
      january: 1,
      feb: 2,
      february: 2,
      mar: 3,
      march: 3,
      apr: 4,
      april: 4,
      may: 5,
      jun: 6,
      june: 6,
      jul: 7,
      july: 7,
      aug: 8,
      august: 8,
      sep: 9,
      sept: 9,
      september: 9,
      oct: 10,
      october: 10,
      nov: 11,
      november: 11,
      dec: 12,
      december: 12,
    };

    const anchors = [
      "valid",
      "validity",
      "until",
      "expiry",
      "expired",
      "expiration",
      "expire",
      "berlaku",
      "hingga",
      "sampai",
      "유효",
      "만료",
      "유효기간",
      "기간",
      "~",
    ];

    const candidates = [];

    function addCandidate(dateText, index, raw, pattern) {
      if (!dateText) return;

      const start = Math.max(0, index - 100);
      const end = Math.min(low.length, index + 140);
      const around = low.slice(start, end);
      const hasAnchor = anchors.some((anchor) => around.includes(anchor));

      candidates.push({
        date: dateText,
        raw,
        source,
        pattern,
        score: hasAnchor ? 90 : 50,
        reason: hasAnchor ? "anchor 주변 날짜" : "일반 날짜 후보",
      });
    }

    for (const m of text.matchAll(/(20\d{2})[.\-/년\s]+(0?[1-9]|1[0-2])[.\-/월\s]+(0?[1-9]|[12]\d|3[01])/g)) {
      addCandidate(
        toIsoDate(m[1], m[2], m[3]),
        m.index || 0,
        m[0],
        "YYYY-MM-DD"
      );
    }

    for (const m of text.matchAll(/\b(0?[1-9]|[12]\d|3[01])\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(20\d{2})\b/gi)) {
      addCandidate(
        toIsoDate(m[3], monthMap[m[2].toLowerCase()], m[1]),
        m.index || 0,
        m[0],
        "DD Month YYYY"
      );
    }

    for (const m of text.matchAll(/\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(0?[1-9]|[12]\d|3[01]),?\s+(20\d{2})\b/gi)) {
      addCandidate(
        toIsoDate(m[3], monthMap[m[1].toLowerCase()], m[2]),
        m.index || 0,
        m[0],
        "Month DD YYYY"
      );
    }

    const unique = new Map();

    for (const item of candidates) {
      if (!item.date) continue;

      const prev = unique.get(item.date);

      if (!prev || Number(item.score || 0) > Number(prev.score || 0)) {
        unique.set(item.date, item);
      }
    }

    return Array.from(unique.values())
      .sort((a, b) => Number(b.score || 0) - Number(a.score || 0))
      .slice(0, 8);
  }

  function mergeDateCandidates(...lists) {
    const unique = new Map();

    for (const list of lists) {
      for (const item of list || []) {
        if (!item?.date) continue;

        const prev = unique.get(item.date);

        if (!prev || Number(item.score || 0) > Number(prev.score || 0)) {
          unique.set(item.date, item);
        }
      }
    }

    return Array.from(unique.values())
      .sort((a, b) => Number(b.score || 0) - Number(a.score || 0))
      .slice(0, 8);
  }


  function normalizeCertText(value) {
    return String(value || "")
      .replace(/&nbsp;/gi, " ")
      .replace(/\r/g, "\n")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function normalizeLoose(value) {
    return String(value || "")
      .toUpperCase()
      .replace(/Ⓡ/g, "R")
      .replace(/[^A-Z0-9]+/g, "")
      .trim();
  }

  function compactCompanyName(value) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!text) return "";

    const stopWords = [
      " 3000 ", " 15024 ", " 1900 ", " 103,", " POL.", " UNIT ",
      " 2 RUE", " 56 GRAND", " P.O.", " PO BOX", " LAAN "
    ];

    const upper = text.toUpperCase();
    let cut = text.length;

    for (const word of stopWords) {
      const idx = upper.indexOf(word);
      if (idx > 0) cut = Math.min(cut, idx);
    }

    return text.slice(0, cut).replace(/[,:\-\s]+$/g, "").trim() || text;
  }

  function countryFromText(value) {
    const upper = String(value || "").toUpperCase();

    const countries = [
      ["UNITED STATES", "USA"],
      [" U.S.A", "USA"],
      [" USA", "USA"],
      ["KOREA", "KOREA"],
      ["THAILAND", "THAILAND"],
      ["MALAYSIA", "MALAYSIA"],
      ["INDONESIA", "INDONESIA"],
      ["NETHERLANDS", "NETHERLANDS"],
      ["UNITED KINGDOM", "UNITED KINGDOM"],
      [" U.K", "UNITED KINGDOM"],
      ["SPAIN", "SPAIN"],
      ["FRANCE", "FRANCE"],
      ["CHINA", "CHINA"],
      ["BRAZIL", "BRAZIL"],
    ];

    for (const [needle, country] of countries) {
      if (upper.includes(needle)) return country;
    }

    return "";
  }

  function certCountryByOrg(org) {
    const key = String(org || "").toUpperCase();
    const map = {
      IFANCA: "USA",
      ISA: "USA",
      KMF: "KOREA",
      JAKIM: "MALAYSIA",
      CICOT: "THAILAND",
      BPJPH: "INDONESIA",
      MUI: "INDONESIA",
      HQC: "NETHERLANDS",
      HCE: "UNITED KINGDOM",
      HFCE: "BELGIUM",
      HFQ: "SPAIN",
      HCA: "AUSTRALIA",
    };

    return map[key] || "";
  }

  function monthToNumber(monthText) {
    const key = String(monthText || "").toLowerCase().slice(0, 3);
    const map = {
      jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
      jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
    };
    return map[key] || 0;
  }

  function extractFirstDateByRegex(text, regexes) {
    for (const regex of regexes) {
      const match = String(text || "").match(regex);
      if (!match) continue;

      if (match.groups?.y && match.groups?.m && match.groups?.d) {
        return toIsoDate(match.groups.y, match.groups.m, match.groups.d);
      }

      if (match.groups?.month && match.groups?.day && match.groups?.year) {
        return toIsoDate(match.groups.year, monthToNumber(match.groups.month), match.groups.day);
      }

      if (match.groups?.day && match.groups?.month && match.groups?.year) {
        return toIsoDate(match.groups.year, monthToNumber(match.groups.month), match.groups.day);
      }
    }

    return "";
  }

  function findLineAfterLabel(lines, labelRegex) {
    const idx = lines.findIndex((line) => labelRegex.test(line));
    if (idx < 0) return "";

    for (let i = idx + 1; i < Math.min(lines.length, idx + 4); i += 1) {
      const value = String(lines[i] || "").trim();
      if (value && !labelRegex.test(value)) return value;
    }

    return "";
  }

  function cleanCompanyNameFromAddress(value) {
    const text = String(value || "")
      .replace(/\s+/g, " ")
      .trim();

    if (!text || text === "-") return "";

    // comma 앞 회사명 우선: Kalizea, 2 rue... -> Kalizea
    if (text.includes(",")) {
      const first = text.split(",", 1)[0].trim();
      if (first) return first;
    }

    const markers = [
      /\b\d{1,6}\b/i,
      /\bSTREET\b/i,
      /\bDRIVE\b/i,
      /\bROAD\b/i,
      /\bRD\b/i,
      /\bAVENUE\b/i,
      /\bAVE\b/i,
      /\bCORPORATE\b/i,
      /\bCENTER\b/i,
      /\bBUILDING\b/i,
      /\bWESTCHESTER\b/i,
      /\bILLINOIS\b/i,
      /\bPENNSYLVANIA\b/i,
      /\bUSA\b/i,
      /\bFRANCE\b/i,
      /\bGERMANY\b/i,
      /\bKOREA\b/i,
      /\bTHAILAND\b/i,
      /\bMALAYSIA\b/i,
    ];

    const positions = markers
      .map((regex) => {
        const match = text.match(regex);
        return match?.index ?? -1;
      })
      .filter((pos) => pos > 2);

    if (positions.length > 0) {
      return text.slice(0, Math.min(...positions)).trim(" ,-");
    }

    return text;
  }

  function normalizeProductNameForMatch(value) {
    return String(value || "")
      .toUpperCase()
      .replace(/[®™]/g, "")
      .replace(/\{.*?FAMILY OF PRODUCTS.*?\}/gi, "")
      .replace(/FAMILY OF PRODUCTS/gi, "")
      .replace(/[^A-Z0-9]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function productMatchScore(expected, candidate) {
    const a = normalizeProductNameForMatch(expected);
    const b = normalizeProductNameForMatch(candidate);

    if (!a || !b) return 0;
    if (a === b) return 100;
    if (a.includes(b) || b.includes(a)) return 92;

    const as = new Set(a.split(" ").filter(Boolean));
    const bs = new Set(b.split(" ").filter(Boolean));

    let hit = 0;
    as.forEach((token) => {
      if (bs.has(token)) hit += 1;
    });

    return Math.round((hit / Math.max(as.size, bs.size, 1)) * 85);
  }

  function parseEnglishDateToIso(value) {
    const monthMap = {
      JANUARY: "01",
      FEBRUARY: "02",
      MARCH: "03",
      APRIL: "04",
      MAY: "05",
      JUNE: "06",
      JULY: "07",
      AUGUST: "08",
      SEPTEMBER: "09",
      OCTOBER: "10",
      NOVEMBER: "11",
      DECEMBER: "12",
    };

    const text = String(value || "").replace(/\s+/g, " ").trim();

    let match = text.match(
      /(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})/i
    );

    if (match) {
      return `${match[3]}-${monthMap[match[1].toUpperCase()]}-${String(match[2]).padStart(2, "0")}`;
    }

    match = text.match(
      /(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s*(20\d{2})/i
    );

    if (match) {
      return `${match[3]}-${monthMap[match[2].toUpperCase()]}-${String(match[1]).padStart(2, "0")}`;
    }

    return "";
  }

  function parseMalayDateToIso(value) {
    const monthMap = {
      JAN: "01",
      JANUARI: "01",
      FEB: "02",
      FEBRUARI: "02",
      MAC: "03",
      MARCH: "03",
      APR: "04",
      APRIL: "04",
      MEI: "05",
      MAY: "05",
      JUN: "06",
      JUNE: "06",
      JUL: "07",
      JULAI: "07",
      AUG: "08",
      OGOS: "08",
      SEP: "09",
      SEPTEMBER: "09",
      OKT: "10",
      OKTOBER: "10",
      NOV: "11",
      NOVEMBER: "11",
      DIS: "12",
      DISEMBER: "12",
    };

    const text = String(value || "").replace(/\s+/g, " ").trim();

    const match = text.match(/(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})/i);
    if (!match) return "";

    const month = monthMap[match[2].toUpperCase()];
    if (!month) return "";

    return `${match[3]}-${month}-${String(match[1]).padStart(2, "0")}`;
  }

  function inferMalaysiaCountry(text) {
    const upper = String(text || "").toUpperCase();

    const malaysiaMarkers = [
      "MALAYSIA",
      "SELANGOR",
      "SHAH ALAM",
      "KUALA LUMPUR",
      "JOHOR",
      "PENANG",
      "PULAU PINANG",
      "KEDAH",
      "KELANTAN",
      "MELAKA",
      "NEGERI SEMBILAN",
      "PAHANG",
      "PERAK",
      "PERLIS",
      "SABAH",
      "SARAWAK",
      "TERENGGANU",
      "PUTRAJAYA",
      "LABUAN",
    ];

    return malaysiaMarkers.some((marker) => upper.includes(marker))
      ? "MALAYSIA"
      : "";
  }

  function isHalalControlNoiseLine(line) {
    const text = String(line || "").trim();
    const upper = text.toUpperCase();

    if (!text) return true;

    if (/^[\u0600-\u06FF\s\W_]+$/.test(text)) return true;

    return [
      "MANUFACTURED BY",
      "اﻟﻣﺻﻧﻌﺔ",
      "المصنعة",
      "ﻓﻲ",
      "في",
    ].some((word) => upper.includes(word));
  }

  function looksLikeHalalControlCompany(line) {
    const text = String(line || "").trim();
    const upper = text.toUpperCase();

    if (!text) return false;
    if (isHalalControlNoiseLine(text)) return false;

    if (/\b\d{4,6}\b/.test(text) && /\([A-Za-z ]+\)/.test(text)) {
      return false;
    }

    return [
      "GMBH",
      "KG",
      "CO.",
      "CO,",
      "LTD",
      "LIMITED",
      "AG",
      "INC",
      "CORPORATION",
      "LLC",
      "S.A.",
      "SAS",
    ].some((token) => upper.includes(token));
  }

  function countryFromParentheses(line) {
    const text = String(line || "");
    const match = text.match(/\((Germany|France|Netherlands|China|Korea|USA|Thailand|Vietnam|Spain|Denmark|Hungary)\)/i);

    if (!match) return "";

    return countryFromText(match[1]);
  }

  function extractIfancaFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const lines = raw
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    const expected = expectedInfo || {};
    const expectedEnglish = expected.englishName || "";

    const companyBlock =
      raw.match(
        /Company\s+Name\s*&\s*Address\s*:?\s*([\s\S]*?)(?:Plant\s+Name\s*&\s*Address|Muhammad|President|This Certificate|Page)/i
      )?.[1] || "";

    const companyFirstLine =
      companyBlock
        .split(/\n/)
        .map((line) => line.trim())
        .filter(Boolean)[0] || "";

    const maker = cleanCompanyNameFromAddress(companyFirstLine);

    const plantBlock =
      raw.match(
        /Plant\s+Name\s*&\s*Address\s*:?\s*([\s\S]*?)(?:Muhammad|President|This Certificate|Page)/i
      )?.[1] || "";

    const country =
      countryFromText(plantBlock) ||
      countryFromText(companyBlock) ||
      "USA";

    const expiryRaw =
      raw.match(/This Certificate is valid until\s+(.+?)\s+and subject/i)?.[1] ||
      raw.match(/This certificate is valid until\s+(.+?)\s+and subject/i)?.[1] ||
      "";

    const expiry = parseEnglishDateToIso(expiryRaw);

    const products = [];

    for (let i = 0; i < lines.length; i += 1) {
      const match = lines[i].match(/^(\d+)\.\s*(.+)$/);

      if (!match) continue;

      const no = Number(match[1]);
      let name = match[2]
        .replace(/\{.*?Family of products.*?\}/gi, "")
        .replace(/\{.*?\}/g, "")
        .replace(/\s+/g, " ")
        .trim();

      if (!name || /^THIS IS TO|^DATE:|^DOCUMENT/i.test(name)) continue;

      const lookAhead = lines.slice(i + 1, i + 8).join("\n");

      const halalId =
        lookAhead.match(/\b[A-Z]\d{5}\b/)?.[0] || "";

      const productCertNo =
        lookAhead.match(/\bHC-[A-Z0-9]{4,}\b/i)?.[0]?.toUpperCase() || "";

      products.push({
        no,
        name,
        halalId,
        certNo: productCertNo,
      });
    }

    const bestProduct =
      products
        .map((product) => ({
          ...product,
          score: productMatchScore(expectedEnglish, product.name),
        }))
        .sort((a, b) => b.score - a.score)[0] || null;

    const selectedProduct =
      bestProduct && bestProduct.score >= 45
        ? bestProduct
        : products[0] || null;

    return {
      supplier: maker || "-",
      koreanName: expected.koreanName || "-",
      englishName:
        selectedProduct?.name ||
        expected.englishName ||
        "-",
      product_name: selectedProduct?.name || "",
      maker: maker || "-",
      org: "IFANCA",
      certNo: selectedProduct?.certNo || "-",
      expiry: expiry || "-",
      country: country || "-",
      certCountry: "USA",
      products,
      best_product_match: selectedProduct
        ? {
            product: {
              name: selectedProduct.name,
              cert_no: selectedProduct.certNo,
              halal_id: selectedProduct.halalId,
            },
            score: selectedProduct.score || 0,
          }
        : null,
    };
  }

  function extractIsaFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const company = raw.match(/Company:\s*([\s\S]*?)(?:\n\s*This certificate|\n\s*This certificate states)/i)?.[1] || "";
    const expiry = extractFirstDateByRegex(raw, [
      /Valid Until:\s*\n?\s*(?<day>\d{1,2})\s+(?<month>[A-Za-z]+)\s+(?<year>20\d{2})/i,
    ]);
    const certNo = raw.match(/Certificate No\.\s*([A-Z0-9\-]+)/i)?.[1] || "";

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(company),
      org: "ISA",
      certNo,
      expiry,
      country: countryFromText(company),
      certCountry: "USA",
    };
  }

  function extractHfceFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const certNo = raw.match(/Document No\.?:\s*\n?\s*([^\n]+)/i)?.[1]?.trim() || "";
    const maker = raw.match(/For:\s*([^\n]+)/i)?.[1]?.trim() || raw.match(/This is to certify that\s+([^,\n]+)/i)?.[1]?.trim() || "";
    const locationBlock = raw.match(/following location:\s*\n?-?\s*([^\n]+)/i)?.[1] || raw;
    const expiry = extractFirstDateByRegex(raw, [
      /Valid until:\s*(?<month>[A-Za-z]+)\s+(?<day>\d{1,2}),?\s+(?<year>20\d{2})/i,
    ]);

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "HFCE",
      certNo,
      expiry,
      country: countryFromText(locationBlock),
      certCountry: "BELGIUM",
    };
  }

  function extractHfqCertNo(raw) {
    const text = String(raw || "")
      .replace(/\r/g, "\n")
      .replace(/[：]/g, ":")
      .replace(/[–—]/g, "-");

    const patterns = [
      /With\s+certificate\s+number\s*:?\s*(HFQ\s*-\s*\d{1,6}\s*\/\s*\d{1,4}\s*\/\s*[A-Z]{2,10})\b/i,
      /Con\s+n[ºo]\s+de\s+certificado\s*:?\s*(HFQ\s*-\s*\d{1,6}\s*\/\s*\d{1,4}\s*\/\s*[A-Z]{2,10})\b/i,
      /\b(HFQ\s*-\s*\d{1,6}\s*\/\s*\d{1,4}\s*\/\s*[A-Z]{2,10})\b/i,
    ];

    for (const pattern of patterns) {
      const match = text.match(pattern);

      if (match?.[1]) {
        return match[1].replace(/\s+/g, "").toUpperCase();
      }
    }

    return "";
  }

  function extractHfqFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const maker = raw.match(/CERTIFY THAT THE COMPANY:\s*CERTIFICA QUE LA EMPRESA:\s*\n?\s*([^\n]+)/i)?.[1] || "";
    const certNo = extractHfqCertNo(raw);
    
    const expiry = extractFirstDateByRegex(raw, [
      /Certificate valid until\s*\n?\s*(?<month>[A-Za-z]+)\s+(?<day>\d{1,2}),?\s+(?<year>20\d{2})/i,
      /Certificado válido hasta\s*\n?\s*(?<day>\d{1,2})\s+de\s+(?<month>[A-Za-z]+),?\s+(?<year>20\d{2})/i,
    ]);
    const plantBlock = raw.match(/Planta auditada[\s\S]*?Spain/i)?.[0] || raw;

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "HFQ",
      certNo: certNo || "-",
      expiry,
      country: countryFromText(plantBlock),
      certCountry: "SPAIN",
    };
  }

  function extractMuiFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const certNo = raw.match(/No\s*:\s*\n?\s*(LPPOM-[A-Z0-9]+)/i)?.[1] || raw.match(/\bLPPOM-[A-Z0-9]+\b/i)?.[0] || "";
    const maker = raw.match(/Name of Company\s*:?\s*\n?\s*([^\n:]+)/i)?.[1] || "";
    const expiry = extractFirstDateByRegex(raw, [
      /Valid until\s*:?\s*(?<month>[A-Za-z]+)\s+(?<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?<year>20\d{2})/i,
    ]);

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "MUI",
      certNo,
      expiry,
      country: countryFromText(maker),
      certCountry: "INDONESIA",
    };
  }

  function extractCicotFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const lines = raw
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    const expected = expectedInfo || {};

    function normalizeName(value) {
      return String(value || "")
        .toUpperCase()
        .replace(/[®™]/g, "")
        .replace(/[^A-Z0-9]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();
    }

    function productScore(a, b) {
      const x = normalizeName(a);
      const y = normalizeName(b);

      if (!x || !y) return 0;
      if (x === y) return 100;
      if (x.includes(y) || y.includes(x)) return 90;

      const xs = new Set(x.split(" ").filter(Boolean));
      const ys = new Set(y.split(" ").filter(Boolean));

      let hit = 0;
      xs.forEach((token) => {
        if (ys.has(token)) hit += 1;
      });

      return Math.round((hit / Math.max(xs.size, ys.size, 1)) * 80);
    }

    function parseCicotDate(value) {
      const monthMap = {
        JANUARY: "01",
        FEBRUARY: "02",
        MARCH: "03",
        APRIL: "04",
        MAY: "05",
        JUNE: "06",
        JULY: "07",
        AUGUST: "08",
        SEPTEMBER: "09",
        OCTOBER: "10",
        NOVEMBER: "11",
        DECEMBER: "12",
      };

      const match = String(value || "").match(
        /(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(20\d{2})/i
      );

      if (!match) return "";

      const month = monthMap[match[1].toUpperCase()];
      const day = String(match[2]).padStart(2, "0");
      const year = match[3];

      return `${year}-${month}-${day}`;
    }

    // 1) 제조사: CERTIFIES THAI / CERTIFIES THAT 바로 아래 회사명
    let maker = "";

    for (let i = 0; i < lines.length; i += 1) {
      const upperLine = lines[i].toUpperCase();

      if (upperLine.includes("CERTIFIES THAI") || upperLine.includes("CERTIFIES THAT")) {
        for (let j = i + 1; j < Math.min(lines.length, i + 6); j += 1) {
          const candidate = lines[j];

          if (
            /CO\.?,?\s*LTD\.?/i.test(candidate) ||
            /LIMITED/i.test(candidate) ||
            /COMPANY/i.test(candidate)
          ) {
            maker = candidate.trim();
            break;
          }
        }
      }

      if (maker) break;
    }

    // fallback: THAI EDIBLE OIL CO.,LTD. 같은 회사명 라인 직접 탐색
    if (!maker) {
      const companyLine = lines.find((line) =>
        /CO\.?,?\s*LTD\.?/i.test(line)
      );

      maker = companyLine || "";
    }

    // 2) 제품명: ProductType: 아래 comma-separated 목록
    const productBlockMatch = raw.match(
      /Product\s*Type\s*:?\s*([\s\S]*?)(?:Factory\s+Address|Undertakes|The\s+Central\s+Islamic|Effective\s+from|Regrsuation|Registration|Issued\s+on)/i
    );

    let productNames = [];

    if (productBlockMatch?.[1]) {
      productNames = productBlockMatch[1]
        .split(/\s*,\s*/)
        .map((name) => name.trim())
        .filter((name) => name.length >= 3)
        .filter((name) => !/^[^A-Za-z0-9]+$/.test(name));
    }

    const expectedEnglish = expected.englishName || "";
    let bestProduct = productNames[0] || "";

    if (expectedEnglish && productNames.length > 0) {
      bestProduct = productNames
        .map((name) => ({
          name,
          score: productScore(expectedEnglish, name),
        }))
        .sort((a, b) => b.score - a.score)[0]?.name || bestProduct;
    }

    // 3) 인증번호: Regrsuation/Registration No. CICOT HL: 다음 값
    const certNo =
      raw.match(/(?:Regrsuation|Registration)\s+No\.?\s+CICOT\s+HL\s*:?\s*\n?\s*([0-9/.-]+)/i)?.[1] ||
      "";

    // 4) 유효기간: Effective from 아래 날짜 2개 중 두 번째
    let expiry = "";

    const effectiveIndex = raw.toUpperCase().indexOf("EFFECTIVE FROM");

    if (effectiveIndex >= 0) {
      const chunk = raw.slice(effectiveIndex, effectiveIndex + 360);
      const dateMatches = Array.from(
        chunk.matchAll(
          /(January|February|March|April|May|June|July|August|September|October|November|December)\s*\d{1,2}(?:st|nd|rd|th)?\s*,?\s*20\d{2}/gi
        )
      ).map((m) => parseCicotDate(m[0]));

      expiry = dateMatches[1] || dateMatches[0] || "";
    }

    // 5) 제조국: Factory Address 블록에서 Thailand
    let country = "";

    const factoryMatch = raw.match(
      /Factory\s+Address\s*:?\s*([\s\S]*?)(?:Undertakes|The\s+Central\s+Islamic|Effective\s+from|Regrsuation|Registration)/i
    );

    if (factoryMatch?.[1]) {
      country = countryFromText(factoryMatch[1]) || "";
    }

    if (!country && raw.toUpperCase().includes("THAILAND")) {
      country = "THAILAND";
    }

    return {
      supplier: maker || "-",
      koreanName: expected.koreanName || "-",
      englishName: bestProduct || expected.englishName || "-",
      product_name: bestProduct || "",
      product_names: productNames,
      maker: maker || "-",
      org: "CICOT",
      certNo: certNo || "-",
      expiry: expiry || "-",
      country: country || "-",
      certCountry: "THAILAND",
    };
  }


  function extractHceFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const maker = raw.match(/Company Name:\s*([^\n]+)/i)?.[1] || "";
    const plant = raw.match(/Manufacture Site:\s*([^\n]+)/i)?.[1] || maker;
    const certNo = raw.match(/Certificate No:\s*([^\n]+)/i)?.[1]?.trim() || "";
    const expiry = extractFirstDateByRegex(raw, [
      /Expiry Date:\s*(?<day>\d{1,2})(?:st|nd|rd|th)?\s+(?<month>[A-Za-z]+)\s+(?<year>20\d{2})/i,
    ]);

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "HCE",
      certNo,
      expiry,
      country: countryFromText(plant),
      certCountry: "UNITED KINGDOM",
    };
  }

  function extractHqcFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const maker = findLineAfterLabel(raw.split(/\n/).map((line) => line.trim()).filter(Boolean), /Awarded to:/i);
    const certNo = raw.match(/Cert\. No:\s*\n?\s*([A-Z0-9]+)/i)?.[1] || "";
    const expiry = extractFirstDateByRegex(raw, [
      /Expiry Date:\s*\n?\s*(?<day>\d{1,2})[\/\-.](?<m>\d{1,2})[\/\-.](?<y>20\d{2})/i,
    ]);
    const companyBlock = raw.match(/Awarded to:[\s\S]*?Halal Quality Control BV/i)?.[0] || raw;

    return {
      englishName: expectedInfo?.englishName || "",
      maker: compactCompanyName(maker),
      org: "HQC",
      certNo,
      expiry,
      country: countryFromText(companyBlock),
      certCountry: "NETHERLANDS",
    };
  }

  function extractHalalControlFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const lines = raw
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    let maker = "";
    let country = "";

    const idx = lines.findIndex((line) =>
      line.toUpperCase().includes("MANUFACTURED BY")
    );

    if (idx >= 0) {
      for (let i = idx + 1; i < Math.min(lines.length, idx + 10); i += 1) {
        const candidate = lines[i];

        if (looksLikeHalalControlCompany(candidate)) {
          maker = candidate.trim();
          break;
        }
      }

      for (let i = idx + 1; i < Math.min(lines.length, idx + 10); i += 1) {
        const candidateCountry = countryFromParentheses(lines[i]);

        if (candidateCountry) {
          country = candidateCountry;
          break;
        }
      }
    }

    const certNo =
      raw.match(/Cert\.-No\.:\s*([A-Z0-9\-\/]+)/i)?.[1] ||
      raw.match(/Certificate Registration No\.:\s*\n?\s*([A-Z0-9\-\/]+)/i)?.[1] ||
      "";

    const expiry = extractFirstDateByRegex(raw, [
      /Valid until:\s*\n?\s*(?<y>20\d{2})[-./](?<m>\d{1,2})[-./](?<d>\d{1,2})/i,
      /This certificate is valid until:\s*\n?\s*(?<y>20\d{2})[-./](?<m>\d{1,2})[-./](?<d>\d{1,2})/i,
      /This certificate is valid until\s+(?<y>20\d{2})[-./](?<m>\d{1,2})[-./](?<d>\d{1,2})/i,
    ]);

    return {
      englishName: expectedInfo?.englishName || "",
      maker,
      org: "HALAL CONTROL",
      certNo,
      expiry,
      country,
      certCountry: "GERMANY",
    };
  }

  function extractJakimFields(text, expectedInfo) {
    const raw = normalizeCertText(text);
    const lines = raw
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    const expected = expectedInfo || {};
    const expectedEnglish = expected.englishName || "";

    let maker = "";

    const makerIndex = lines.findIndex((line) =>
      /Manufactured\s*\/\s*distributed\s*\/\s*managed\s+by/i.test(line)
    );

    if (makerIndex >= 0) {
      maker = lines[makerIndex + 1] || "";
    }

    const addressBlock =
      makerIndex >= 0
        ? lines.slice(makerIndex + 2, makerIndex + 7).join("\n")
        : "";

    const country =
      countryFromText(addressBlock) ||
      inferMalaysiaCountry(addressBlock) ||
      "MALAYSIA";

    const certNo =
      raw.match(/No\.\s*Ruj\s*:\s*\/\s*Ref\s*No\.?\s*:?\s*\n?\s*([A-Z0-9.\-/ ]+)/i)?.[1]?.trim() ||
      raw.match(/\bJAKIM\.[A-Z0-9.\-/ ]+/i)?.[0]?.trim() ||
      raw.match(/Reference\s*:?\s*[\s\S]{0,80}?\b(E\d{4,})\b/i)?.[1]?.trim() ||
      "";

    const expiryRaw =
      raw.match(/Sah\s+Sehingga\s*\/\s*Valid\s+until\s*:?\s*\n?\s*([^\n]+)/i)?.[1] ||
      "";

    const expiry = parseMalayDateToIso(expiryRaw);

    const productBlock =
      raw.match(
        /It is hereby certified that\s*:?\s*([\s\S]*?)(?:yang dikeluarkan|Manufactured\s*\/\s*distributed\s*\/\s*managed\s+by)/i
      )?.[1] ||
      raw.match(
        /Adalah dengan ini diperakukan\s*:?\s*([\s\S]*?)(?:yang dikeluarkan|Manufactured\s*\/\s*distributed\s*\/\s*managed\s+by)/i
      )?.[1] ||
      "";

    const products = [];

    productBlock
      .split(/\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .forEach((line) => {
        const match = line.match(/^(\d+)\.\s*(.+)$/);

        if (!match) return;

        products.push({
          no: Number(match[1]),
          name: match[2].replace(/\s+/g, " ").trim(),
        });
      });

    const bestProduct =
      products
        .map((product) => ({
          ...product,
          score: productMatchScore(expectedEnglish, product.name),
        }))
        .sort((a, b) => b.score - a.score)[0] || null;

    const selectedProduct =
      bestProduct && bestProduct.score >= 45
        ? bestProduct
        : products[0] || null;

    return {
      supplier: maker || "-",
      koreanName: expected.koreanName || "-",
      englishName:
        selectedProduct?.name ||
        expected.englishName ||
        "-",
      product_name: selectedProduct?.name || "",
      maker: maker || "-",
      org: "JAKIM",
      certNo: certNo || "-",
      expiry: expiry || "-",
      country: country || "-",
      certCountry: "MALAYSIA",
      products,
      best_product_match: selectedProduct
        ? {
            product: {
              name: selectedProduct.name,
            },
            score: selectedProduct.score || 0,
          }
        : null,
    };
  }

  function extractOcrCertificateFields(rawText, expectedInfo, orgCandidates) {
    const text = normalizeCertText(rawText);
    const upper = text.toUpperCase();
    const expected = expectedInfo || {};

    let result = {
      supplier: "-",
      koreanName: expected.koreanName || "-",
      englishName: expected.englishName || "-",
      maker: "-",
      org: (orgCandidates || []).join(", ") || "-",
      certNo: "-",
      expiry: "-",
      country: "-",       // 제조국
      certCountry: "-",   // 인증국가
      countryOrgMatch: "-",
    };

    const primaryOrg =
      upper.includes("THE CENTRAL ISLAMIC COUNCIL OF THAILAND") ? "CICOT" :
      upper.includes("HALAL CONTROL") ? "HALAL CONTROL" :
      (upper.includes("JABATAN KEMAJUAN ISLAM MALAYSIA") || upper.includes("HALAL MALAYSIA") || upper.includes("JAKIM")) ? "JAKIM" :
      (upper.includes("ISLAMIC FOOD AND NUTRITION COUNCIL OF AMERICA") || upper.includes("IFANCA")) ? "IFANCA" :
      (upper.includes("ISLAMIC SERVICES OF AMERICA") || /\bISA\b/.test(upper)) ? "ISA" :
      upper.includes("HALAL FOOD COUNCIL OF EUROPE") ? "HFCE" :
      upper.includes("HALAL FOOD & QUALITY") ? "HFQ" :
      upper.includes("HALAL CERTIFICATION EUROPE") ? "HCE" :
      upper.includes("HALAL QUALITY CONTROL") ? "HQC" :
      upper.includes("MAJELIS ULAMA INDONESIA") || upper.includes("LPPOM MUI") ? "MUI" :
      upper.includes("REPUBLIK INDONESIA") || upper.includes("SERTIFIKAT HALAL") || /\bID00\d{8,}/.test(upper) ? "BPJPH" :
      (orgCandidates || [])[0] || "";

    const ruleMap = {
      IFANCA: extractIfancaFields,
      ISA: extractIsaFields,
      HFCE: extractHfceFields,
      HFQ: extractHfqFields,
      HCE: extractHceFields,
      HQC: extractHqcFields,
      MUI: extractMuiFields,
      CICOT: extractCicotFields,
      JAKIM: extractJakimFields,
    };

    if (typeof extractHalalControlFields === "function") {
      ruleMap["HALAL CONTROL"] = extractHalalControlFields;
    }

    if (typeof extractBpjphFields === "function") {
      ruleMap.BPJPH = extractBpjphFields;
    }

    const extracted = ruleMap[primaryOrg]
      ? ruleMap[primaryOrg](text, expected)
      : {};

    result = {
      ...result,
      ...extracted,
      org: extracted.org || primaryOrg || result.org,
      expiry:
        extracted.expiry ||
        mergeDateCandidates(extractDateCandidates(text, "ocr"))[0]?.date ||
        "-",
    };

    if (result.org === "HFQ") {
      const hfqCertNo = extractHfqCertNo(text);

      result.certNo = hfqCertNo || "-";
    }
    
    if (!result.certCountry || result.certCountry === "-") {
      result.certCountry = certCountryByOrg(result.org) || "-";
    }

    const makerCountry = normalizeLoose(result.country);
    const certCountry = normalizeLoose(result.certCountry);

    if (
      makerCountry &&
      certCountry &&
      result.country !== "-" &&
      result.certCountry !== "-"
    ) {
      result.countryOrgMatch = makerCountry === certCountry ? "일치" : "불일치";
    }

    return result;
  }

  function normalizeMatchText(value) {
    return String(value || "")
      .toUpperCase()
      .replace(/[^A-Z0-9가-힣]/g, "");
  }

  function getOrgAliases(org) {
    const key = String(org || "").toUpperCase();

    const aliasMap = {
      KMF: ["KMF", "KOREA MUSLIM FEDERATION"],
      CICOT: ["CICOT", "CENTRAL ISLAMIC COUNCIL OF THAILAND", "THE CENTRAL ISLAMIC COUNCIL OF THAILAND"],
      IFANCA: ["IFANCA", "ISLAMIC FOOD AND NUTRITION COUNCIL OF AMERICA"],
      HQC: ["HQC", "HALAL QUALITY CONTROL"],
      HCA: ["HCA", "HALAL CERTIFICATION AUTHORITY"],
      ISA: ["ISA", "ISLAMIC SERVICES OF AMERICA"],
      JAKIM: ["JAKIM", "JABATAN KEMAJUAN ISLAM MALAYSIA"],
      BPJPH: ["BPJPH", "BADAN PENYELENGGARA JAMINAN PRODUK HALAL"],
      MUI: ["MUI", "MAJELIS ULAMA INDONESIA"],
    };

    return aliasMap[key] || [key];
  }

  function scoreLhlnRecord(record, orgCandidates) {
    const orgs = orgCandidates || [];
    const aliases = orgs.flatMap((org) => getOrgAliases(org));

    const recordText = normalizeMatchText([
      record.country,
      record.negara,
      record.org_name,
      record.nama_lhln,
      record.name,
      record.agency,
      record.agency_name,
      record.short_name,
      record.abbr,
      record.abbreviation,
      record.city,
      record.kota,
      record.registration_no,
      record.no_reg,
    ].join(" "));

    let bestScore = 0;
    let matchedAlias = "";

    aliases.forEach((alias) => {
      const aliasText = normalizeMatchText(alias);

      if (!aliasText) return;

      let score = 0;

      if (recordText === aliasText) {
        score = 100;
      } else if (recordText.includes(aliasText)) {
        score = 85;
      } else if (aliasText.includes(recordText) && recordText.length >= 4) {
        score = 70;
      }

      if (score > bestScore) {
        bestScore = score;
        matchedAlias = alias;
      }
    });

    return {
      score: bestScore,
      matchedAlias,
    };
  }

  function findBestLhlnMatch(orgCandidates) {
    const orgs = orgCandidates || [];

    if (orgs.includes("BPJPH") || orgs.includes("MUI")) {
      return null;
    }

    const scored = (lhlnRecords || [])
      .map((record) => {
        const result = scoreLhlnRecord(record, orgs);

        return {
          ...record,
          _score: result.score,
          _matchedAlias: result.matchedAlias,
        };
      })
      .filter((record) => record._score > 0)
      .sort((a, b) => b._score - a._score);

    return scored[0] || null;
  }

  function buildLhlnDecision(orgCandidates) {
    const orgs = orgCandidates || [];
    const bestMatch = findBestLhlnMatch(orgs);

    if (orgs.includes("BPJPH") || orgs.includes("MUI")) {
      return {
        label: "LHLN 매칭 생략",
        status: "skip",
        match: null,
        desc: "BPJPH/MUI는 인도네시아 기관으로 관리하며, 현재 로직에서는 LHLN 교차인정 확인 대상에서 제외합니다.",
      };
    }

    if (bestMatch) {
      return {
        label: "LHLN 매칭 후보",
        status: "ok",
        match: bestMatch,
        desc: `${bestMatch._matchedAlias || "기관 후보"} 기준으로 LHLN 후보가 확인되었습니다.`,
      };
    }

    if (orgs.length === 0) {
      return {
        label: "기관 후보 없음",
        status: "unknown",
        match: null,
        desc: "OCR 원문/파일명/메일 제목에서 인증기관 후보를 찾지 못했습니다.",
      };
    }

    return {
      label: "LHLN 확인 필요",
      status: "check",
      match: null,
      desc: "기관 후보는 있으나 LHLN DB에서 직접 매칭되는 항목을 찾지 못했습니다.",
    };
  }

  async function loadOcrData(next = {}) {
    try {
      setLoading(true);

      const status = next.status ?? ocrHistoryStatusFilter;
      const org = next.org ?? ocrHistoryOrgFilter;
      const keyword = next.keyword ?? ocrHistoryKeyword;

      const [targetData, jobData, mailTargetData, logData, lhlnData] = await Promise.all([
        getInboxOcrTargets({ limit: 500, only_pending: false }),
        getOcrJobs({
          limit: 300,
          status,
          org,
          keyword,
          include_test: false,
        }),
        getMailTargets({ testMode: false }),
        getMailLogs({ limit: 500, testMode: false }),
        getLhlnRecords({ limit: 500 }),
      ]);

      setOcrTargets(targetData.rows || []);
      setJobs(jobData.rows || []);
      setMailTargets(mailTargetData.rows || mailTargetData.targets || []);
      setMailLogs(logData.rows || []);
      setLhlnRecords(lhlnData.rows || []);

      setCheckedOcrJobIds((prev) => {
        const valid = new Set((jobData.rows || []).map((job) => Number(job.id)));
        return prev.filter((id) => valid.has(Number(id)));
      });
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }
  

  useEffect(() => {
    loadOcrData();
  }, []);

  const targetByPath = useMemo(() => {
    const map = new Map();

    for (const row of ocrTargets) {
      if (row.saved_path) {
        map.set(normalizePath(row.saved_path), row);
      }
    }

    return map;
  }, [ocrTargets]);

  function findTargetByAnyPath(pathText) {
    const normalized = normalizePath(pathText);

    if (!normalized) return null;

    for (const row of ocrTargets) {
      const saved = normalizePath(row.saved_path);

      if (!saved) continue;

      if (normalized === saved) return row;
      if (normalized.endsWith(saved)) return row;
      if (saved.endsWith(normalized)) return row;
    }

    return null;
  }

  function getJobMeta(job) {
    const target = findTargetByAnyPath(job?.source_path);
    const mailTarget = target?.request_id
      ? mailTargetByRequestId.get(target.request_id)
      : null;
    const mailLog = target?.request_id
      ? mailLogByRequestId.get(target.request_id)
      : null;
    const logInfo = extractExpectedInfoFromMailText([
      mailLog?.subject,
      mailLog?.body_html,
      mailTarget?.subject,
      mailTarget?.body_html,
      target?.subject,
      target?.body_text,
      target?.body_preview,
    ].join("\n"));

    const orgs = inferOrgCandidates(
      job?.filename,
      job?.source_path,
      target?.subject,
      target?.saved_filename,
      target?.original_filename
    );

    const filenameCandidates = parseJsonArray(target?.filename_date_candidates_json);
    const mailCandidates = parseJsonArray(target?.mail_date_candidates_json);
    const jobFilenameCandidates = extractDateCandidates(job?.filename, "filename");

    const dateCandidates = mergeDateCandidates(
      filenameCandidates,
      mailCandidates,
      jobFilenameCandidates
    );

    return {
      target,
      mailTarget,
      supplier:
        logInfo.supplier ||
        pickFirst(mailTarget, ["supplier", "supplier_name", "vendor"]) ||
        pickFirst(target, ["sender"]) ||
        "-",
      material:
        logInfo.koreanName ||
        pickFirst(mailTarget, [
          "material_name",
          "main_material",
          "korean_name",
          "product_name",
          "item_name",
        ]) ||
        "-",
      org: orgs.join(", ") || "-",
      expiry: dateCandidates[0]?.date || "-",
      requestId: target?.request_id || "-",
    };
  }

  function getJobImageClassification(job) {
    return (
      job?.image_classification ||
      job?.result?.image_classification ||
      job?.result?.field_guess?.image_classification ||
      {}
    );
  }

  function getTemplateDecisionLabel(value) {
    const text = String(value || "").toUpperCase();

    if (text === "AUTO_IMAGE") return "자동";
    if (text === "REVIEW") return "검토";
    if (text === "MANUAL_REVIEW") return "수동";
    if (text === "EXCLUDED") return "제외";
    if (text === "ERROR") return "오류";
    if (text === "AUTO_CONFIRMED") return "확정";
    if (text === "MANUAL_CONFIRMED") return "확정";
    if (text === "MANUAL_CORRECTED") return "정정";
    if (text === "RESTORED") return "복구";

    return text || "-";
  }

  function getTemplateClassificationSummary(job) {
    const info = getJobImageClassification(job);

    if (!info) {
      return {
        predictedOrg: "-",
        finalOrg: "-",
        imageDecision: "-",
        adminDecision: "-",
        scoreText: "-",
        label: "-",
        isExcluded: false,
        title: "양식 DB 분류 정보 없음",
      };
    }

    const predictedOrg = info.predicted_org || "-";
    const finalOrg = info.is_excluded ? "-" : (info.final_org || predictedOrg || "-");
    const imageDecision = info.image_decision || info.decision || "-";
    const adminDecision = info.admin_decision || info.manual_decision?.decision_type || "";
    const score = Number(info.score);
    const scoreText = Number.isFinite(score) ? score.toFixed(4) : "-";
    const margin = Number(info.margin);
    const marginText = Number.isFinite(margin) ? margin.toFixed(4) : "-";

    const labelParts = [getTemplateDecisionLabel(imageDecision)];

    if (adminDecision) {
      labelParts.push(getTemplateDecisionLabel(adminDecision));
    }

    if (info.is_excluded) {
      labelParts.push("OCR제외");
    }

    return {
      predictedOrg,
      finalOrg,
      imageDecision,
      adminDecision,
      scoreText,
      marginText,
      label: labelParts.filter(Boolean).join(" / "),
      isExcluded: Boolean(info.is_excluded),
      title: [
        `이미지기관: ${predictedOrg}`,
        `최종기관: ${finalOrg}`,
        `이미지판정: ${getTemplateDecisionLabel(imageDecision)}`,
        adminDecision ? `관리자판정: ${getTemplateDecisionLabel(adminDecision)}` : "",
        `score: ${scoreText}`,
        `margin: ${marginText}`,
        info.second_org ? `2순위: ${info.second_org}` : "",
      ]
        .filter(Boolean)
        .join("\n"),
    };
  }

  const mailTargetByRequestId = useMemo(() => {
    const map = new Map();

    for (const row of mailTargets) {
      if (row.request_id) {
        map.set(row.request_id, row);
      }
    }

    return map;
  }, [mailTargets]);

  const mailLogByRequestId = useMemo(() => {
    const map = new Map();

    for (const row of mailLogs) {
      if (!row.request_id) continue;
      if (!map.has(row.request_id)) {
        map.set(row.request_id, row);
      }
    }

    return map;
  }, [mailLogs]);

  const candidateFiles = useMemo(() => {
    const targetRows = ocrTargets.map((row) => ({
      kind: "inbox_target",
      id: `target-${row.id}`,
      filepath: row.saved_path,
      filename: row.saved_filename || row.original_filename || "-",
      file_ext: row.ext || "",
      size_bytes: row.file_size || 0,
      modified_at: row.received_at || row.created_at || "-",
      request_id: row.request_id || "",
      ocr_status: row.ocr_status || "pending",
      ocr_selected: Number(row.ocr_selected || 0),
      source_row: row,
    }));

    const targetPaths = new Set(
      targetRows.map((row) => normalizePath(row.filepath))
    );

    const normalRows = files
      .filter((file) => !targetPaths.has(normalizePath(file.filepath)))
      .map((file) => ({
        kind: "file",
        id: `file-${file.filepath}`,
        filepath: file.filepath,
        filename: file.filename,
        file_ext: file.file_ext,
        size_bytes: file.size_bytes,
        modified_at: file.modified_at,
        request_id: "",
        ocr_status: "",
        ocr_selected: 0,
        source_row: file,
      }));

    return [...targetRows, ...normalRows];
  }, [ocrTargets, files]);

  const filteredFiles = useMemo(() => {
    const q = fileKeyword.trim().toLowerCase();

    if (!q) return candidateFiles;

    return candidateFiles.filter((file) => {
      const text = [
        file.filename,
        file.filepath,
        file.file_ext,
        file.modified_at,
        file.request_id,
        file.ocr_status,
      ]
        .join(" ")
        .toLowerCase();

      return text.includes(q);
    });
  }, [candidateFiles, fileKeyword]);

  const selectedFile =
    candidateFiles.find((file) => normalizePath(file.filepath) === normalizePath(selectedPath)) ||
    filteredFiles[0];

  const selectedTarget =
    findTargetByAnyPath(selectedJob?.source_path) ||
    findTargetByAnyPath(selectedFile?.filepath) ||
    null;

  const selectedMailTarget = selectedTarget?.request_id
    ? mailTargetByRequestId.get(selectedTarget.request_id)
    : null;

  const selectedMailLog = selectedTarget?.request_id
    ? mailLogByRequestId.get(selectedTarget.request_id)
    : null;

  const selectedJobRawText = selectedJob?.raw_text || selectedJob?.raw_text_preview || "";
  const jobOrgCandidates = selectedJob?.result?.field_guess?.org_candidates || [];

  const inferredOrgCandidates = inferOrgCandidates(
    selectedJob?.filename,
    selectedJob?.source_path,
    selectedTarget?.subject,
    selectedTarget?.saved_filename,
    selectedTarget?.original_filename,
    selectedMailTarget?.subject,
    selectedJobRawText
  );

  const orgCandidates = Array.from(
    new Set([...jobOrgCandidates, ...inferredOrgCandidates])
  );

  const filenameDateCandidates = parseJsonArray(
    selectedTarget?.filename_date_candidates_json
  );

  const mailDateCandidates = parseJsonArray(
    selectedTarget?.mail_date_candidates_json
  );

  const ocrDateCandidates = extractDateCandidates(selectedJobRawText, "ocr");

  const mergedDateCandidates = mergeDateCandidates(
    ocrDateCandidates,
    filenameDateCandidates,
    mailDateCandidates
  );

  const bestExpiry = mergedDateCandidates[0]?.date || "-";
  const lhlnDecision = buildLhlnDecision(orgCandidates);

  const mailTextInfo = extractExpectedInfoFromMailText([
    selectedMailLog?.subject,
    selectedMailLog?.body_html,
    selectedMailLog?.body_text,
    selectedTarget?.subject,
    selectedTarget?.body_text,
    selectedTarget?.body_preview,
    selectedMailTarget?.subject,
    selectedMailTarget?.body,
    selectedMailTarget?.body_html,
    selectedMailTarget?.content,
  ].join("\n"));

  const expectedInfo = {
    supplier:
      mailTextInfo.supplier ||
      pickFirst(selectedMailTarget, ["supplier", "supplier_name", "vendor", "company_name"]) ||
      pickFirst(selectedTarget, ["sender"]) ||
      "-",

    koreanName:
      mailTextInfo.koreanName ||
      pickFirst(selectedMailTarget, [
        "material_name",
        "main_material",
        "korean_name",
        "product_name",
        "item_name",
        "raw_material",
        "display_material",
      ]) ||
      "-",

    englishName:
      mailTextInfo.englishName ||
      pickFirst(selectedMailTarget, [
        "english_name",
        "main_english",
        "product_english",
        "material_english",
        "display_english",
      ]) ||
      "-",

    maker:
      mailTextInfo.maker ||
      pickFirst(selectedMailTarget, [
        "maker",
        "manufacturer",
        "display_maker",
      ]) ||
      "-",

    org:
      mailTextInfo.org ||
      pickFirst(selectedMailTarget, [
        "org",
        "main_org",
        "cert_org",
        "certification_body",
        "display_org",
      ]) ||
      orgCandidates[0] ||
      "-",

    certNo:
      mailTextInfo.certNo ||
      pickFirst(selectedMailTarget, [
        "cert_no",
        "certificate_no",
        "cert_number",
        "display_cert_no",
      ]) ||
      "-",

    expiry:
      mailTextInfo.expiry ||
      pickFirst(selectedMailTarget, [
        "exp",
        "expiry",
        "valid_until",
        "valid_date",
        "display_exp",
      ]) ||
      "-",

    country:
      mailTextInfo.country ||
      pickFirst(selectedMailTarget, [
        "maker_country",
        "country",
        "manufacture_country",
        "display_country",
      ]) ||
      "-",
  };

  const ocrReadInfo = extractOcrCertificateFields(
    selectedJobRawText,
    expectedInfo,
    orgCandidates
  );

  function buildOcrHighlightTerms(rule, expected, readInfo) {
    const terms = [];

    function add(label, value, className) {
      const text = String(value || "").trim();
      if (!text || text === "-" || text.length < 3) return;

      terms.push({
        label,
        value: text,
        className,
      });
    }

    add("제품명", rule?.best_product_match?.product?.name, "hl-product");
    add("제품명", rule?.product_name, "hl-product");
    add("제품명", expected?.englishName, "hl-product");
    add("제품명", readInfo?.englishName, "hl-product");
    add("제품명", expected?.koreanName, "hl-product");

    add("제조사", rule?.manufacturer, "hl-maker");
    add("제조사", expected?.maker, "hl-maker");
    add("제조사", readInfo?.maker, "hl-maker");

    add("인증기관", rule?.cert_org, "hl-org");
    add("인증기관", expected?.org, "hl-org");
    add("인증기관", readInfo?.org, "hl-org");

    add("인증번호", rule?.cert_no, "hl-cert");
    add("인증번호", expected?.certNo, "hl-cert");
    add("인증번호", readInfo?.certNo, "hl-cert");

    add("유효기간", rule?.expiry_date, "hl-expiry");
    add("유효기간", expected?.expiry, "hl-expiry");
    add("유효기간", readInfo?.expiry, "hl-expiry");
    add("유효기간", bestExpiry, "hl-expiry");

    add("제조국", rule?.manufacturing_country, "hl-mfg-country");
    add("제조국", expected?.country, "hl-mfg-country");
    add("제조국", readInfo?.country, "hl-mfg-country");
    add("인증국가", rule?.cert_country, "hl-cert-country");
    add("인증국가", readInfo?.certCountry, "hl-cert-country");

    const seen = new Set();

    return terms
      .filter((item) => {
        const key = item.value.toUpperCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((a, b) => b.value.length - a.value.length);
  }

  function escapeRegExp(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function HighlightedOcrText({ text, rule, expected, readInfo }) {
    const source = String(text || "");
    const terms = buildOcrHighlightTerms(rule, expected, readInfo);

    if (!source.trim()) {
      return <>추출된 텍스트가 없습니다.</>;
    }

    if (terms.length === 0) {
      return <>{source}</>;
    }

    const pattern = new RegExp(
      `(${terms.map((item) => escapeRegExp(item.value)).join("|")})`,
      "gi"
    );

    return (
      <>
        {source.split(pattern).map((part, idx) => {
          const found = terms.find(
            (item) => item.value.toUpperCase() === String(part).toUpperCase()
          );

          if (!found) {
            return <span key={`ocr-text-${idx}`}>{part}</span>;
          }

          return (
            <mark
              key={`ocr-mark-${idx}`}
              className={`ocr-highlight ${found.className}`}
              title={found.label}
            >
              {part}
            </mark>
          );
        })}
      </>
    );
  }

  async function handleRunOcr() {
    if (!selectedFile?.filepath) {
      alert("OCR 처리할 파일을 선택하세요.");
      return;
    }

    try {
      setLoading(true);

      const result = await createOcrJob({
        source_path: selectedFile.filepath,
        ocr_scanned_pages: ocrScannedPages,
        lang: ocrLang,
      });

      const detail = await getOcrJob(result.id);
      setSelectedJob(detail);

      await loadOcrData();

      alert(`OCR 처리 완료: ${detail.status}`);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function toggleOcrFileChecked(filepath) {
    if (!filepath) return;

    setCheckedOcrFilePaths((prev) => {
      if (prev.includes(filepath)) {
        return prev.filter((x) => x !== filepath);
      }

      return [...prev, filepath];
    });
  }

  function handleSelectAllOcrFiles() {
    setCheckedOcrFilePaths(
      filteredFiles
        .map((file) => file.filepath)
        .filter(Boolean)
    );
  }

  function handleClearOcrFiles() {
    setCheckedOcrFilePaths([]);
  }

  async function handleRunCheckedOcr() {
    const targets = filteredFiles.filter((file) =>
      checkedOcrFilePaths.includes(file.filepath)
    );

    if (targets.length === 0) {
      alert("OCR 실행할 후보 파일을 체크하세요.");
      return;
    }

    const ok = window.confirm(`체크한 파일 ${targets.length}건을 OCR 실행합니다. 계속할까요?`);
    if (!ok) return;

    try {
      setLoading(true);

      let lastDetail = null;

      for (const file of targets) {
        const result = await createOcrJob({
          source_path: file.filepath,
          ocr_scanned_pages: ocrScannedPages,
          lang: ocrLang,
        });

        lastDetail = await getOcrJob(result.id);
      }

      if (lastDetail) {
        setSelectedJob(lastDetail);
        if (lastDetail.source_path) {
          setSelectedPath(lastDetail.source_path);
        }
      }

      setCheckedOcrFilePaths([]);
      await loadOcrData();

      alert(`OCR 처리 완료: ${targets.length}건`);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectJob(jobId) {
    try {
      setLoading(true);
      const detail = await getOcrJob(jobId);
      setSelectedJob(detail);

      if (detail.source_path) {
        setSelectedPath(detail.source_path);
      }
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }
  
  function toggleOcrJobChecked(jobId) {
    const id = Number(jobId);

    if (!id) return;

    setCheckedOcrJobIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((x) => x !== id);
      }

      return [...prev, id];
    });
  }

  function handleSelectAllOcrJobs() {
    setCheckedOcrJobIds(jobsForView.map((job) => Number(job.id)).filter(Boolean));
  }

  function handleClearOcrJobChecks() {
    setCheckedOcrJobIds([]);
  }

  async function handleDeleteSelectedOcrJobs() {
    if (checkedOcrJobIds.length === 0) {
      alert("삭제할 OCR 작업을 선택하세요.");
      return;
    }

    const ok = window.confirm(`선택한 OCR 작업 ${checkedOcrJobIds.length}건을 삭제합니다. 계속할까요?`);
    if (!ok) return;

    try {
      setLoading(true);

      await deleteOcrJobs(checkedOcrJobIds);

      if (selectedJob?.id && checkedOcrJobIds.includes(Number(selectedJob.id))) {
        setSelectedJob(null);
      }

      setCheckedOcrJobIds([]);
      await loadOcrData();

      alert("선택 OCR 작업 삭제 완료");
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRerunSelectedOcrJobs() {
    const targets = jobsForView.filter((job) =>
      checkedOcrJobIds.includes(Number(job.id))
    );

    if (targets.length === 0) {
      alert("재판독할 OCR 작업을 선택하세요.");
      return;
    }

    const ok = window.confirm(`선택한 OCR 작업 ${targets.length}건을 재판독합니다. 계속할까요?`);
    if (!ok) return;

    try {
      setLoading(true);

      let lastDetail = null;

      for (const job of targets) {
        if (!job.source_path) continue;

        const result = await createOcrJob({
          source_path: job.source_path,
          ocr_scanned_pages: ocrScannedPages,
          lang: ocrLang,
        });

        lastDetail = await getOcrJob(result.id);
      }

      if (lastDetail) {
        setSelectedJob(lastDetail);
      }

      setCheckedOcrJobIds([]);
      await loadOcrData();

      alert("선택 OCR 작업 재판독 완료");
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleManualFilePick(fileList) {
    const picked = Array.from(fileList || []);

    if (picked.length === 0) return;

    setManualUploadFiles((prev) => {
      const map = new Map();

      [...prev, ...picked].forEach((file) => {
        const key = `${file.name}_${file.size}_${file.lastModified}`;
        map.set(key, file);
      });

      return Array.from(map.values());
    });
  }

  function handleRemoveManualFile(index) {
    setManualUploadFiles((prev) => prev.filter((_, idx) => idx !== index));
  }

  async function handleUploadManualOcrFiles() {
    if (manualUploadFiles.length === 0) {
      alert("추가할 인증서 파일을 선택하세요.");
      return;
    }

    try {
      setLoading(true);

      const uploadResult = await uploadOcrManualFiles(manualUploadFiles);
      const uploadedRows = (uploadResult.rows || []).filter((row) => row.ok && row.saved_path);

      if (uploadedRows.length === 0) {
        alert("업로드된 OCR 대상 파일이 없습니다.");
        return;
      }

      let lastDetail = null;

      for (const row of uploadedRows) {
        const result = await createOcrJob({
          source_path: row.saved_path,
          ocr_scanned_pages: ocrScannedPages,
          lang: ocrLang,
        });

        lastDetail = await getOcrJob(result.id);
      }

      if (lastDetail) {
        setSelectedJob(lastDetail);
      }

      setManualUploadFiles([]);
      await loadOcrData();

      alert(`수동 파일 ${uploadedRows.length}건 OCR 등록 완료`);
    } catch (err) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleCandidateKeyDown(e) {
    if (!filteredFiles.length) return;

    const currentIndex = Math.max(
      filteredFiles.findIndex(
        (file) => normalizePath(file.filepath) === normalizePath(selectedFile?.filepath)
      ),
      0
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(currentIndex + 1, filteredFiles.length - 1);
      setSelectedPath(filteredFiles[nextIndex].filepath);
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.max(currentIndex - 1, 0);
      setSelectedPath(filteredFiles[nextIndex].filepath);
    }
  }

  const jobsForView = useMemo(() => {
    const sorted = [...jobs].sort((a, b) => Number(b.id || 0) - Number(a.id || 0));
    const map = new Map();

    for (const job of sorted) {
      const meta = getJobMeta(job);

      const key = meta.requestId && meta.requestId !== "-"
        ? `${meta.requestId}__${job.filename || ""}`
        : normalizePath(job.source_path || job.filename || job.id);

      if (!map.has(key)) {
        map.set(key, job);
      }
    }

    return Array.from(map.values());
  }, [jobs, ocrTargets, mailTargets, mailLogs]);

  function handleJobKeyDown(e) {
    if (!jobsForView.length) return;

    const currentIndex = Math.max(
      jobsForView.findIndex((job) => job.id === selectedJob?.id),
      0
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = Math.min(currentIndex + 1, jobsForView.length - 1);
      handleSelectJob(jobsForView[nextIndex].id);
    }

    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.max(currentIndex - 1, 0);
      handleSelectJob(jobsForView[nextIndex].id);
    }
  }

  const doneCount = jobsForView.filter((job) => job.status === "DONE").length;
  const noTextCount = jobsForView.filter((job) => job.status === "NO_TEXT").length;
  const errorCount = jobsForView.filter((job) => job.status === "ERROR").length;
  const pendingTargetCount = ocrTargets.filter((row) =>
    ["pending", "error", "not_run", ""].includes(String(row.ocr_status || "pending"))
  ).length;

  return (
    <>
      <PageHeader
        eyebrow="OCR / AI"
        title="인증서 판독"
        desc="수신메일 OCR 대상과 OCR 작업 이력을 연결해 인증기관, 유효기간 후보, LHLN 확인 필요 여부를 검토합니다."
        onBack={() => setActive("home")}
      />

      <StatLine
        items={[
          { label: "OCR 대상", value: ocrTargets.length },
          { label: "대기/오류", value: pendingTargetCount },
          { label: "OCR 완료", value: doneCount },
          { label: "오류", value: errorCount },
        ]}
      />
      <section
        className={
          manualUploadOpen
            ? "ocr-manual-upload-mini ocr-collapsible-panel is-open"
            : "ocr-manual-upload-mini ocr-collapsible-panel is-collapsed"
        }
      >
        <div className="ocr-manual-upload-head ocr-collapsible-head">
          <div>
            <span>MANUAL ADD</span>
            <strong>수동 파일 추가</strong>
          </div>

          <div className="ocr-collapse-head-actions">
            <small>선택 {manualUploadFiles.length}건</small>
            <button
              type="button"
              className="ocr-collapse-toggle"
              aria-expanded={manualUploadOpen}
              onClick={() => setManualUploadOpen((open) => !open)}
            >
              {manualUploadOpen ? "접기 ▲" : "펼치기 ▼"}
            </button>
          </div>
        </div>

        {manualUploadOpen ? (
          <div className="ocr-collapsible-body">
            <div className="ocr-manual-upload-actions ocr-manual-upload-controls">
              <select value={ocrLang} onChange={(e) => setOcrLang(e.target.value)}>
                <option value="eng">eng</option>
                <option value="kor+eng">kor+eng</option>
              </select>

              <label className="check-pill">
                <input
                  type="checkbox"
                  checked={ocrScannedPages}
                  onChange={(e) => setOcrScannedPages(e.target.checked)}
                />
                <span>스캔 PDF OCR 시도</span>
              </label>
            </div>

            <div
              className={manualDragActive ? "ocr-manual-dropzone active" : "ocr-manual-dropzone"}
              onDragOver={(e) => {
                e.preventDefault();
                setManualDragActive(true);
              }}
              onDragLeave={() => setManualDragActive(false)}
              onDrop={(e) => {
                e.preventDefault();
                setManualDragActive(false);
                handleManualFilePick(e.dataTransfer.files);
              }}
              onClick={() => manualUploadInputRef.current?.click()}
            >
              <input
                ref={manualUploadInputRef}
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp"
                onChange={(e) => handleManualFilePick(e.target.files)}
                hidden
              />

              <strong>파일 드래그 또는 클릭</strong>
              <span>PDF / 이미지 인증서를 수동으로 추가합니다.</span>
            </div>

            {manualUploadFiles.length > 0 ? (
              <div className="ocr-manual-file-strip">
                {manualUploadFiles.map((file, idx) => (
                  <button
                    key={`${file.name}_${file.size}_${file.lastModified}`}
                    type="button"
                    onClick={() => handleRemoveManualFile(idx)}
                    title="클릭하면 목록에서 제거"
                  >
                    <strong>{file.name}</strong>
                    <span>{formatBytes(file.size)}</span>
                  </button>
                ))}
              </div>
            ) : null}

            <div className="ocr-manual-bottom">
              <span>선택 {manualUploadFiles.length}건</span>

              <button
                type="button"
                className="primary-button"
                onClick={handleUploadManualOcrFiles}
                disabled={loading || manualUploadFiles.length === 0}
              >
                {loading ? "처리 중..." : "수동 파일 OCR 등록"}
              </button>
            </div>
          </div>
        ) : null}
      </section>
      

      <section className="ocr-history-wide-surface ocr-history-main-panel">
        <div className="ocr-history-head compact single-line">
          <div className="ocr-history-title-inline">
            <div className="surface-title">OCR 작업 이력</div>
            <p>수신메일 첨부파일 및 수동 등록 파일의 OCR 결과를 확인합니다.</p>
          </div>
        </div>

        <div className="ocr-history-toolbar one-line">
          <input
            value={ocrHistoryKeyword}
            onChange={(e) => setOcrHistoryKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                loadOcrData({ keyword: ocrHistoryKeyword });
              }
            }}
            placeholder="업체명 / 원료명 / 파일명 / 인증번호 검색"
          />

          <select
            value={ocrHistoryOrgFilter}
            onChange={(e) => {
              const value = e.target.value;
              setOcrHistoryOrgFilter(value);
              loadOcrData({ org: value });
            }}
          >
            <option value="">전체 기관</option>
            <option value="BPJPH">BPJPH</option>
            <option value="MUI">MUI</option>
            <option value="IFANCA">IFANCA</option>
            <option value="HQC">HQC</option>
            <option value="ISA">ISA</option>
            <option value="LLS-ISA">LLS-ISA</option>
            <option value="JAKIM">JAKIM</option>
            <option value="MUIS">MUIS</option>
            <option value="HCE">HCE</option>
            <option value="HFCE">HFCE</option>
            <option value="HFQ">HFQ</option>
            <option value="CICOT">CICOT</option>
            <option value="HALAL CONTROL">HALAL CONTROL</option>
          </select>

          <select
            value={ocrHistoryStatusFilter}
            onChange={(e) => {
              const value = e.target.value;
              setOcrHistoryStatusFilter(value);
              loadOcrData({ status: value });
            }}
          >
            <option value="">전체 상태</option>
            <option value="DONE">DONE</option>
            <option value="NO_TEXT">NO_TEXT</option>
            <option value="ERROR">ERROR</option>
            <option value="SCANNED_NEED_OCR">스캔본</option>
            <option value="TESSERACT_ERROR">Tesseract 오류</option>
          </select>

          <button
            type="button"
            className="ghost-action"
            onClick={() => loadOcrData({ keyword: ocrHistoryKeyword })}
            disabled={loading}
          >
            검색
          </button>

          <button
            type="button"
            className="ghost-action"
            onClick={() => loadOcrData()}
            disabled={loading}
          >
            새로고침
          </button>

          <button
            type="button"
            className="ghost-action"
            onClick={handleSelectAllOcrJobs}
            disabled={loading || jobsForView.length === 0}
          >
            전체선택
          </button>

          <button
            type="button"
            className="ghost-action"
            onClick={handleClearOcrJobChecks}
            disabled={loading || checkedOcrJobIds.length === 0}
          >
            전체해제
          </button>

          <button
            type="button"
            className="ghost-action danger"
            onClick={handleDeleteSelectedOcrJobs}
            disabled={loading || checkedOcrJobIds.length === 0}
          >
            선택삭제
          </button>

          <button
            type="button"
            className="primary-button"
            onClick={handleRerunSelectedOcrJobs}
            disabled={loading || checkedOcrJobIds.length === 0}
          >
            선택 재판독
          </button>
        </div>

        <div className="ocr-history-table-scroll">
          <div className="ocr-history-table-head with-check compact">
            <div>선택</div>
            <div>업체명</div>
            <div>제품/원료명</div>
            <div>이미지기관</div>
            <div>최종기관</div>
            <div>분류상태</div>
            <div>유효기간후보</div>
            <div>OCR상태</div>
            <div>파일명</div>
            <div>처리일</div>
          </div>

          <div
            className="ocr-history-table-body compact"
            ref={jobListRef}
            tabIndex={0}
            onKeyDown={handleJobKeyDown}
          >
            {jobsForView.length === 0 ? (
              <div className="mail-log-empty">
                OCR 작업 이력이 없습니다.
              </div>
            ) : (
              jobsForView.map((job) => {
                const meta = getJobMeta(job);
                const rule =
                  job.certificate_rule ||
                  job.result?.certificate_rule ||
                  job.result?.field_guess?.certificate_rule ||
                  {};

                const historyOrg = rule.cert_org || meta.org || "-";

                const historyExpiry =
                  rule.cert_org === "BPJPH"
                    ? "유지확인"
                    : rule.expiry_date || meta.expiry || "-";

                const historyMaterial =
                  rule.best_product_match?.product?.name ||
                  meta.material ||
                  "-";

                const templateSummary = getTemplateClassificationSummary(job);

                const effectiveStatus = getEffectiveOcrStatus(job);

                const statusClass =
                  effectiveStatus === "DONE"
                    ? "mini-badge ok"
                    : effectiveStatus === "NO_TEXT" ||
                        effectiveStatus === "SCANNED_NEED_OCR" ||
                        effectiveStatus === "EXCLUDED"
                      ? "mini-badge warn"
                      : "mini-badge fail";

                return (
                  <button
                    key={job.id}
                    type="button"
                    className={
                      selectedJob?.id === job.id
                        ? "ocr-history-row with-check compact active"
                        : "ocr-history-row with-check compact"
                    }
                    onClick={() => handleSelectJob(job.id)}
                  >
                    <div
                      className="ocr-row-check"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={checkedOcrJobIds.includes(Number(job.id))}
                        onChange={() => toggleOcrJobChecked(job.id)}
                      />
                    </div>

                    <EllipsisText
                      value={meta.supplier || "-"}
                      className="ocr-history-cell-center"
                    />

                    <EllipsisText
                      value={historyMaterial}
                      className="is-left history-material-name"
                    />

                    <EllipsisText
                      value={templateSummary.predictedOrg || historyOrg}
                      className="ocr-history-cell-center"
                    />

                    <EllipsisText
                      value={templateSummary.finalOrg || historyOrg}
                      className="ocr-history-cell-center"
                    />

                    <div title={templateSummary.title || ""}>
                      <span className={templateSummary.isExcluded ? "mini-badge warn" : "mini-badge ok"}>
                        {templateSummary.label}
                      </span>
                    </div>

                    <EllipsisText
                      value={historyExpiry}
                      className="ocr-history-cell-center"
                    />

                    <div title={effectiveStatus || ""}>
                      <span className={statusClass}>
                        {effectiveStatus}
                      </span>
                    </div>

                    <EllipsisText
                      value={job.filename || "-"}
                      className="is-left history-file-name"
                    />

                    <div title={job.updated_at || ""}>
                      {formatOcrTableDate(job.updated_at)}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      </section>

      <section
        className={
          ocrResultOpen
            ? "mail-log-preview-surface ocr-preview ocr-preview-refined ocr-collapsible-panel is-open"
            : "mail-log-preview-surface ocr-preview ocr-preview-refined ocr-collapsible-panel is-collapsed"
        }
      >
        <div className="mail-log-preview-head ocr-collapsible-head">
          <div>
            <div className="surface-title fixed-panel-label">OCR 결과</div>
            <div className="ocr-file-title-soft" title={selectedJob?.filename || ""}>
              {selectedJob?.filename || "OCR 작업 이력을 선택하세요."}
            </div>
          </div>

          <div className="preview-badges ocr-collapse-head-actions">
            {selectedJob ? (
              <span className={selectedJob.status === "DONE" ? "mini-badge ok" : "mini-badge fail"}>
                {selectedJob.status}
              </span>
            ) : null}
            <button
              type="button"
              className="ocr-collapse-toggle dark"
              aria-expanded={ocrResultOpen}
              onClick={() => setOcrResultOpen((open) => !open)}
              disabled={!selectedJob}
            >
              {ocrResultOpen ? "접기 ▲" : "펼치기 ▼"}
            </button>
          </div>
        </div>

        {ocrResultOpen ? (
          selectedJob ? (
            <>
            <div className="ocr-meta-grid-refined">
              <div className="ocr-meta-card path">
                <span>파일 경로</span>
                <strong>{selectedJob.source_path}</strong>
              </div>

              <div className="ocr-meta-card small">
                <span>확장자</span>
                <strong>{selectedJob.file_ext}</strong>
              </div>

              <div className="ocr-meta-card small">
                <span>상태</span>
                <strong>{selectedJob.status}</strong>
              </div>

              <div className="ocr-meta-card small">
                <span>오류</span>
                <strong>{selectedJob.error_message || "-"}</strong>
              </div>
            </div>

            <div className="ocr-decision-grid compact-ratio">
              <div className="ocr-decision-card compact">
                <span>기관 후보</span>
                <strong title={orgCandidates.join(", ") || "-"}>
                  {orgCandidates.join(", ") || "-"}
                </strong>
              </div>

              <div className="ocr-decision-card compact">
                <span>유효기간 후보</span>
                <strong title={bestExpiry || "-"}>
                  {bestExpiry || "-"}
                </strong>
              </div>

              <div className={`ocr-decision-card ocr-lhln-mini-card wide ${lhlnDecision.status}`}>
                <div>
                  <span>인증국가</span>
                  <strong
                    title={
                      lhlnDecision.match?.negara ||
                      lhlnDecision.match?.country ||
                      certificateRule?.cert_country ||
                      ocrReadInfo.certCountry ||
                      "-"
                    }
                  >
                    {lhlnDecision.match?.negara ||
                      lhlnDecision.match?.country ||
                      certificateRule?.cert_country ||
                      ocrReadInfo.certCountry ||
                      "-"}
                  </strong>
                </div>

                <div>
                  <span>기관명</span>
                  <strong
                    title={
                      lhlnDecision.match?.nama_lhln ||
                      lhlnDecision.match?.org_name ||
                      lhlnDecision.match?.name ||
                      lhlnDecision.match?.agency ||
                      certificateRule?.cert_org ||
                      orgCandidates[0] ||
                      "-"
                    }
                  >
                    {lhlnDecision.match?.nama_lhln ||
                      lhlnDecision.match?.org_name ||
                      lhlnDecision.match?.name ||
                      lhlnDecision.match?.agency ||
                      certificateRule?.cert_org ||
                      orgCandidates[0] ||
                      "-"}
                  </strong>
                </div>
              </div>
            </div>
            
            {certificateRule ? (
              <div className="ocr-rule-card">
                <div className="ocr-rule-head">
                  <div>
                    <span>CERTIFICATE RULE</span>
                    <strong>규칙 기반 판독결과</strong>
                  </div>

                  <em className={`ocr-rule-status ${certificateRule.parse_status || "UNKNOWN"}`}>
                    {certificateRule.parse_status || "UNKNOWN"}
                  </em>
                </div>

                <div className="ocr-rule-compact">
                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-org">인증기관</span>
                    <strong>{certificateRule.cert_org || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-cert-country">인증국가</span>
                    <strong>{certificateRule.cert_country || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-mfg-country">제조국</span>
                    <strong>{certificateRule.manufacturing_country || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-cert">인증번호</span>
                    <strong>{certificateRule.cert_no || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line">
                    <span className="rule-field-label hl-expiry">유효기간</span>
                    <strong>
                      {certificateRule.cert_org === "BPJPH"
                        ? "유지확인 대상"
                        : certificateRule.expiry_date || "-"}
                    </strong>
                  </div>

                  <div className="ocr-rule-line wide">
                    <span className="rule-field-label hl-maker">제조사</span>
                    <strong>{certificateRule.manufacturer || "-"}</strong>
                  </div>

                  <div className="ocr-rule-line wide">
                    <span className="rule-field-label hl-product">제품명</span>
                    <strong>
                      {certificateRule.best_product_match?.product?.name ||
                        certificateRule.product_name ||
                        ocrReadInfo.englishName ||
                        "-"}
                    </strong>
                  </div>
                </div>
              </div>
            ) : null}      


            <div className="ocr-highlight-legend">
              <span className="hl-product">제품명</span>
              <span className="hl-maker">제조사</span>
              <span className="hl-org">인증기관</span>
              <span className="hl-cert">인증번호</span>
              <span className="hl-expiry">유효기간</span>
              <span className="hl-mfg-country">제조국</span>
              <span className="hl-cert-country">인증국가</span>
            </div>

            <div className="ocr-text-box refined highlighted">
              <HighlightedOcrText
                text={selectedJob.raw_text || selectedJob.raw_text_preview || ""}
                rule={certificateRule}
                expected={expectedInfo}
                readInfo={ocrReadInfo}
              />
            </div>
            </>
          ) : (
            <div className="mail-log-empty">
              OCR 작업을 실행하거나 이력을 선택하면 결과가 표시됩니다.
            </div>
          )
        ) : null}
      </section>
    </>
  );
}

export default OcrPage;
