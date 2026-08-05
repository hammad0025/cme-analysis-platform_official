import {
  filterUsableEvidence,
  NOT_SHOWN_ON_VIDEO,
} from './evidenceQuality';
import { isMetadataClaimId, mergeThreeWayIssues, annotateEgregiousFields } from './egregiousRanking';

/** Merge atomic report claims with claim_verdicts for deposition UI rows. */

function synthesizeVideoShows(verdict) {
  const fromEvidence = filterUsableEvidence(verdict.evidence || [], verdict.claim_id)
    .slice(0, 2)
    .map((e) => String(e.notes || e.quote).trim())
    .filter(Boolean);
  if (fromEvidence.length) return fromEvidence.join(' ');
  const reasoning = String(verdict.reasoning || '');
  return reasoning
    .replace(/Offline heuristic:\s*\d+\s*frame\(s\)\s*matched[^;]*;?\s*/gi, '')
    .replace(/\brun with an API key[^.]*\.?\s*/gi, '')
    .trim();
}

export function mergeDepositionRows(verdicts, atomicClaims, threeWayLedger = null) {
  const byId = {};
  for (const c of atomicClaims?.claims || []) {
    if (c?.claim_id) byId[c.claim_id] = c;
  }

  const merged = mergeThreeWayIssues(verdicts, threeWayLedger);

  return merged
    .filter((v) => !isMetadataClaimId(v?.claim_id))
    .map((v, idx) => {
    const atomic = byId[v.claim_id] || {};
    const reportQuote = atomic.report_quote || v.report_quote || v.claim_text || '';
    const row = {
      ...v,
      _id: v.claim_id || `claim-${idx}`,
      test_name: atomic.test_name || v.test_name || v.claim_id,
      report_page: atomic.report_page ?? v.report_page,
      report_section: atomic.report_section ?? v.report_section,
      report_quote: reportQuote,
      deposition_prompt: atomic.deposition_prompt || v.deposition_prompt || '',
      claim_text: reportQuote || v.claim_text,
      video_shows: (() => {
        const raw = v.video_shows || synthesizeVideoShows(v);
        const usable = filterUsableEvidence(v.evidence || [], v.claim_id);
        if (!usable.length && (v.verdict || '').toLowerCase() === 'not_shown') {
          return NOT_SHOWN_ON_VIDEO;
        }
        if (!usable.length && !raw) return NOT_SHOWN_ON_VIDEO;
        return raw;
      })(),
    };
    return annotateEgregiousFields(row);
  });
}

export async function fetchDepositionRows({ verdictsUrl, atomicUrl }) {
  const [verdictsRes, atomicRes] = await Promise.all([
    fetch(verdictsUrl),
    atomicUrl ? fetch(atomicUrl) : Promise.resolve(null),
  ]);
  if (!verdictsRes?.ok) throw new Error(`Failed to load claim verdicts (${verdictsRes?.status})`);
  const verdicts = await verdictsRes.json();
  const atomic = atomicRes?.ok ? await atomicRes.json() : null;
  return mergeDepositionRows(verdicts, atomic);
}
