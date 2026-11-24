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
  kind:"politics",title:"정부 인사 발표",
  source_title:'국힘 "수능마저 못 믿는 나라…최교진 사퇴로 끝날 일 아냐"'
}),false, "do not let a shortened caption bypass a party-opinion rejection");

assert.equal(allowed({
  kind:"politics",title:"국회 예산안 가결",
  source_title:"미국 의회 선거 결과 발표"
}),false, "foreign source must not become a domestic headline");

assert.equal(allowed({kind:"politics",title:"국회 예산안 가결"}),true,
  "old approved items without source_title still work");
assert.equal(allowed({kind:"earthquake",title:"한반도 인근 규모 4.3 지진 발생"}),true);

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

assert.equal(allowed({kind:"weather",title:"전국 날씨"}),false,
  "unsupported feed types must not reach the overlay");
assert.equal(allowed(null),false);

console.log("OBS display editorial safeguards OK");
