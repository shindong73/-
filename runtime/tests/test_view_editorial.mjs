import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath} from "node:url";
import {runInNewContext} from "node:vm";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "web");
const source = readFileSync(join(root, "view.js"), "utf8");
const first = source.indexOf("  const foreignHeadline = ");
const last = source.indexOf("  function show(item) {", first);
assert(first >= 0 && last > first, "broadcast eligibility section missing");
const allowed = runInNewContext(
  "(() => {" + source.slice(first, last) + " return allowBroadcast; })()"
);

assert.equal(allowed({
  kind:"politics",
  title:"새 후보자 다섯 명 발표",
  source_title:"[속보] 청와대 국정원장 강금실 지명"
}),true, "broadcast rewrite without an actor must not drop approved domestic news");
assert.equal(allowed({
  kind:"politics",
  title:"보건복지부가 지원 대상 확대 발표",
  source_title:"보건복지부, 지원 대상 확대 발표"
}),true, "verified national-ministry policy coverage should reach OBS");

assert.equal(allowed({
  kind:"politics",
  title:"국토교통부가 주택 공급계획 공개",
  source_title:"국토교통부, 주택 공급계획 공개"
}),true, "major national policy news should not be blocked by viewer");


assert.equal(allowed({
  kind:"politics",
  title:"이용철 법무부 장관 후보자 청문보고서, 국회 법사위에서 여당 주도로 채택",
  source_title:"법사위, 與 주도로 이용철 법무 후보자 청문보고서 채택",
  source:"MBC"
}), true, "confirmed law committee hearing-report adoption must pass OBS gate");
assert.equal(allowed({
  kind:"politics",
  title:"이용철 법무부 장관 후보자 청문보고서, 국회 법사위에서 여당 주도로 채택",
  source_title:"[단독] 법사위, 與 주도로 이용철 법무 후보자 청문보고서 채택",
  source:"MBC"
}), false, "exclusive report ban still overrides hearing event");
assert.equal(allowed({
  kind:"politics",
  title:"이용철 법무부 장관 후보자 청문보고서, 국회 법사위에서 채택",
  source_title:"법사위, 조국혁신당 주도로 이용철 법무 후보자 청문보고서 채택",
  source:"MBC"
}), false, "excluded party reports must stay blocked");

assert.equal(allowed({
  kind:"politics",
  title:"최민희 중징계 처분, 당 윤리심판원 의결",
  source_title:'[속보] 민주 윤리심판원 "최민희, 당 품위 훼손‥중징계 의결"',
  source:"MBC"
}), true, "formally adopted high-profile ethics sanction must reach OBS");
assert.equal(allowed({
  kind:"politics",
  title:"최민희 중징계 처분, 당 윤리심판원 의결",
  source_title:'[단독] 민주 윤리심판원 "최민희, 당 품위 훼손‥중징계 의결"',
  source:"MBC"
}), false, "exclusive-label ban remains active for disciplinary news");

assert.equal(allowed({
  kind:"politics",title:"정부 인사 발표",
  source_title:'국힘 "수능마저 못 믿는 나라…최교진 사퇴로 끝날 일 아냐"'
}),false, "do not let a shortened caption bypass a party-opinion rejection");

assert.equal(allowed({
  kind:"politics",title:"국회 예산안 가결",
  source_title:"미국 의회 선거 결과 발표"
}),false, "foreign source must not become a domestic headline");

assert.equal(allowed({
  kind:"politics",
  title:"국회가 주요 법안 처리 결정",
  source_title:"[속보] 조국혁신당, 국회 주요 법안 처리 결정"
}),false,"innovation party articles must be blocked even after headline paraphrasing");
assert.equal(allowed({
  kind:"politics",
  title:"정부가 주요 정책 발표",
  source_title:"혁신당 정책 관련 정부 주요 발표"
}),false,"every innovation-party reference must be excluded");

assert.equal(allowed({kind:"politics",title:"국회 예산안 가결"}),false,
  "legacy unsourced articles must not replay publisher originals");
assert.equal(allowed({kind:"earthquake",title:"한반도 인근 규모 4.3 지진 발생"}),false,
  "old non-test earthquake captions must never replay");
assert.equal(allowed({kind:"earthquake",title:"한반도 인근 규모 4.4 지진 발생",
  source:"USGS",id:"usgs-old-event"}),false,"USGS completely blocked");
assert.equal(allowed({kind:"warning",title:"울릉도 경계경보 발령",
  source_title:"울릉도 경계경보 발령",source:"USGS"}),false,
  "USGS cannot re-enter through a different caption kind");
assert.equal(allowed({kind:"earthquake",title:"[테스트] 지진 모의 상황",
  source:"방송 테스트 · 실제 뉴스 아님",is_test:true}),true,
  "explicit manual simulations can still be tested without live USGS");

assert.equal(allowed({
  kind:"politics",
  title:"특검 출범 후 첫 구속…나머지 선관위 직원 7명 기각",
  source_title:"특검 출범 후 첫 구속…나머지 선관위 직원 7명 기각"
}),false, "no election commission story can appear");
assert.equal(allowed({
  kind:"politics",
  title:"특검 출범…직원 7명 기각",
  source_title:"[속보] 특검 출범 후 첫 구속…선관위 직원 7명 기각"
}),false, "source title exclusion must survive paraphrase");
assert.equal(allowed({
  kind:"politics",
  title:"정부가 선거 조작 수사 발표",
  source_title:"[속보] 정부, 부정선거 조사"
}),false, "fraud headlines must be excluded");
assert.equal(allowed({
  kind:"politics",
  title:"울산시가 이경식 울산경제자유구역청장 해임",
  source_title:"[속보] 울산시, 이경식 울산경제자유구역청장 해임"
}),false, "minor local-government appointment cannot reach OBS");
assert.equal(allowed({
  kind:"politics",
  title:"이 대통령이 신임 교육부 장관 지명",
  source_title:"[속보] 이 대통령, 신임 교육부 장관 지명"
}),true, "national cabinet changes remain eligible");
assert.equal(allowed({
  kind:"politics",
  title:"국회 예산안 가결",
  source_title:"[속보] 국회 예산안 가결"
}),false, "removing a breaking prefix is not a substantive rewrite");
assert.equal(allowed({
  kind:"politics",
  title:"국회가 예산안 가결",
  source_title:"[속보] 국회, 예산안 가결",
  source:"KBS"
}),true, "reworded headline is allowed regardless of internal audit source");


assert.equal(allowed({
  kind:"warning",title:"울릉도 경계경보 발령",
  source_title:"[속보] 러시아 군용기 접근에 울릉도 경계경보 발령"
}),true, "verified regional warning should be displayed as a warning only");
assert.equal(allowed({
  kind:"warning",title:"울릉도 경계경보 해제",
  source_title:"울릉군 경계경보 해제"
}),true, "cancellation must be allowed after the issuance");
assert.equal(allowed({
  kind:"warning",title:"북한 미사일 발사",
  source_title:"북한 미사일 발사"
}),false, "a military headline must never impersonate a warning");
assert.equal(allowed({
  kind:"warning",title:"울릉도 경계경보 발령",
  source_title:"북한 미사일 발사"
}),false, "a made-up warning cannot bypass source validation");
assert.equal(allowed({
  kind:"warning",title:"울릉도 경계경보 발령",
  source_title:"울릉도 경계경보 발령 모의훈련"
}),false, "drill headline must never be mistaken for real warning");
assert.equal(allowed({
  kind:"politics",title:"국회 북한 미사일 대응",
  source_title:"국회 북한 탄도미사일 관련 회의"
}),false, "missile news must be blocked in political feed too");

assert.equal(allowed({
  kind:"politics",
  title:"국회가 예산안 최종 가결",
  source_title:"[단독] 국회, 예산안 최종 가결"
}),false, "original exclusive tag blocks reworded caption");
assert.equal(allowed({
  kind:"warning",
  title:"울릉도 경계경보 발령",
  source_title:"【단독】 울릉도 경계경보 발령"
}),false, "exclusive tag also blocks otherwise real warning");
assert.equal(allowed({
  kind:"politics",
  title:"정부가 정책 발표",
  source_title:"(단독) 정부, 정책 발표"
}),false, "round-bracket exclusive reports blocked");
assert.equal(allowed({
  kind:"politics",
  title:"국회가 주요 법안 가결",
  source_title:"[속보] 국회, 주요 법안 가결"
}),true, "nonexclusive routine national law decision stays allowed");

assert.equal(allowed({
  kind:"politics",title:"핵심 규제 개편안 시행",
  source_title:"핵심 규제 개편안 공식 시행 발표",ai_approved:true
}),false,"historical AI approval must not bypass local editorial checks");
assert.equal(allowed({
  kind:"politics",title:"정부가 주요 예산 확정",
  source_title:"[단독] 정부, 주요 예산 확정",ai_approved:true
}),false,"[단독] remains blocked regardless of legacy AI flag");
assert.equal(allowed({
  kind:"politics",title:"위원회 관련 후속 조치 발표",
  source_title:"선관위, 부정선거 관련 후속 조치 발표",ai_approved:true
}),false,"user election exclusion remains blocked regardless of legacy AI flag");
assert.equal(allowed({
  kind:"politics",title:"새로운 지진 속보",
  source_title:"지진 발생 발표",source:"USGS",ai_approved:true
}),false,"USGS source remains blocked regardless of legacy AI flag");

assert.equal(allowed({kind:"weather",title:"전국 날씨"}),false,
  "unsupported feed types must not reach the overlay");
assert.equal(allowed(null),false);

console.log("OBS rules-only display safeguards OK");
