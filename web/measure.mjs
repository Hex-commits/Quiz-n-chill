/**
 * Measure what actually overflows, at real window sizes.
 *
 * Reports, per viewport: whether the document scrolls, whether <main> scrolls,
 * whether the category board scrolls, and the measured height of every block
 * competing for the column -- so a fix is aimed at the thing that is actually
 * too tall rather than at whichever one I guessed.
 */
import { chromium } from "playwright";

const CODE = process.argv[2];
const PLAYER = process.argv[3];
const SIZES = [
  [1920, 1080],
  [1600, 900],
  [1440, 900],
  [1366, 768],
  [1280, 800],
  [1280, 720],
  [1152, 700],
  [1024, 640],
];

const browser = await chromium.launch();

async function probe(page, url, label) {
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForTimeout(700);

  return await page.evaluate((label) => {
    const box = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      return {
        h: Math.round(el.getBoundingClientRect().height),
        scroll: el.scrollHeight - el.clientHeight,
      };
    };
    const de = document.documentElement;
    const main = document.querySelector("main");
    // The board is the one grid with auto-fill columns.
    const grid = [...document.querySelectorAll("div")].find((d) =>
      typeof d.className === "string" && d.className.includes("auto-fill"),
    );
    const cards = grid ? grid.children.length : 0;
    const cols = grid
      ? getComputedStyle(grid).gridTemplateColumns.split(" ").length
      : 0;
    return {
      label,
      docScroll: de.scrollHeight - de.clientHeight,
      mainScroll: main ? main.scrollHeight - main.clientHeight : null,
      mainH: main ? Math.round(main.getBoundingClientRect().height) : null,
      board: grid
        ? {
            h: Math.round(grid.getBoundingClientRect().height),
            scroll: grid.scrollHeight - grid.clientHeight,
            cards,
            cols,
            cardH: grid.firstElementChild
              ? Math.round(grid.firstElementChild.getBoundingClientRect().height)
              : null,
            w: Math.round(grid.getBoundingClientRect().width),
            tpl: getComputedStyle(grid).gridTemplateColumns,
            gap: getComputedStyle(grid).gap,
          }
        : null,
      header: box("header"),
      footer: box("footer"),
      turnbar: box("main .sticky, main [class*='rounded-'][class*='border']"),
      question: box("main .animate-quiz-rise"),
      qHeader: box("main .animate-quiz-rise > [data-slot='card-header']"),
      qBody: box("main .animate-quiz-rise > [data-slot='card-content']"),
    };
  }, label);
}

for (const [w, h] of SIZES) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  // Without an identity the lobby route renders the rejoin form, not the board.
  if (CODE && PLAYER) {
    await page.addInitScript(
      ([code, id]) => window.localStorage.setItem(`quiz-quiz:player:${code}`, id),
      [CODE, PLAYER],
    );
  }
  const out = [];
  out.push(await probe(page, "http://localhost:3000/play", "start"));
  if (CODE) out.push(await probe(page, `http://localhost:3000/lobby/${CODE}`, "room"));

  for (const r of out) {
    const flag = (n) => (n > 0 ? `SCROLLS +${n}` : "ok");
    console.log(
      `${w}x${h}  ${r.label.padEnd(6)} doc=${flag(r.docScroll).padEnd(12)} ` +
        `main=${flag(r.mainScroll ?? 0).padEnd(12)} ` +
        (r.board
          ? `board=${flag(r.board.scroll).padEnd(12)} h=${r.board.h} cards=${r.board.cards} cols=${r.board.cols} w=${r.board.w} gap=${r.board.gap} cardH=${r.board.cardH} q=${r.question?.h}(head ${r.qHeader?.h} body ${r.qBody?.h})`
          : ""),
    );
  }
  await page.close();
}

await browser.close();
