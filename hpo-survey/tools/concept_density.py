#!/usr/bin/env python3
r"""Concept-density measurement for LaTeX teaching documents.

Measures three dimensions of conceptual pacing, calibrated by running the
same detector over a target document and exemplar documents:

  1. introduction rate  - distinct new concepts per 1000 prose words
  2. consolidation      - occurrences per concept, singleton share, lifetime span
  3. burst / live load  - new concepts per paragraph; distinct concepts
                          first-introduced within a trailing window
                          (operational form of the teaching contract's
                          "live conceptual items" diagnostic)

Concept detectors (applied identically to every document):
  A. acronym / mixed-case method tokens   (ASHA, qNEHVI, BG-PBT, muP)
  B. mid-sentence capitalized tokens      (Hyperband, Chebyshev, Brax)
  C. \emph{...} phrases                   (definition convention)
  D. citation keys                        (each cited work = one concept)
  E. recurring technical bigrams          (trust region, record law)

Usage:
  concept_density.py DOC:file1,file2,...  [DOC2:...]  [--lint DOC]
"""
import re, sys, glob, statistics

STOP = set('''the a an and or of to in on for with by at as is are was were be
been from that this these those it its their our we you they he she not no if
then than but so such via per each both all any some most more less least very
also only even just still yet when where which who whom whose what how why
into over under between across during within without against toward towards
above below after before again once here there now out up down off own same
other another new old first second third last next while because'''.split())

CAP_STOP = set('''The A An In On For With By At As It Its Our We If Then But So
Such Chapter Section Figure Table Equation Part Appendix Chapters Sections
Figures Tables When Where Which Who What How Why This These Those There Here
Now Not No Yes And Or Of To Every Each Both All Any Some Most More Less While
Because Between Across During Within Without Against Two Three Four Five One
Take Suppose Write Let Given Under Assembled Return Returns Consider Start
Recall Note Notably Concretely First Second Third Fourth Finally Both'''.split())

ACRO_STOP = {'II', 'III', 'IV', 'OK', 'PhD', 'ImageNet'}  # ImageNet kept as B


def read_clean(path):
    """Return list of (line_no, cleaned_paragraph, emph_terms, cite_keys)."""
    raw = open(path, encoding='utf-8', errors='ignore').read()
    raw = re.sub(r'(?m)(?<!\\)%.*$', '', raw)
    out = []
    pos_line = 1
    for para in re.split(r'\n\s*\n', raw):
        line_no = pos_line
        pos_line += para.count('\n') + 2
        p = para
        # drop drawing / tabular bodies, keep captions elsewhere
        p = re.sub(r'\\begin\{(tikzpicture|tabular|lstlisting|verbatim)\}.*?'
                   r'\\end\{\1\}', ' ', p, flags=re.S)
        cites = re.findall(r'\\cite[pt]?\*?(?:\[[^\]]*\])?\{([^}]*)\}', p)
        keys = [k.strip() for grp in cites for k in grp.split(',') if k.strip()]
        p = re.sub(r'\\cite[pt]?\*?(?:\[[^\]]*\])?\{[^}]*\}', ' CITEMARK ', p)
        emphs = [re.sub(r'\s+', ' ', m).strip().lower()
                 for m in re.findall(r'\\emph\{([^{}]{3,60})\}', p)]
        emphs = [e for e in emphs if re.match(r'^[a-z][a-z -]+$', e)]
        # math out, keep a marker for display counting
        p = re.sub(r'\\begin\{(equation|align|gather|multline)\*?\}.*?'
                   r'\\end\{\1\*?\}', ' MATHDISP ', p, flags=re.S)
        p = re.sub(r'\\\[.*?\\\]', ' MATHDISP ', p, flags=re.S)
        p = re.sub(r'\$\$.*?\$\$', ' MATHDISP ', p, flags=re.S)
        p = re.sub(r'\$[^$]*\$', ' ', p)
        p = re.sub(r'\\\(.*?\\\)', ' ', p, flags=re.S)
        p = re.sub(r'\\(label|ref|eqref|pageref|cref|autoref|input|include|'
                   r'includegraphics|bibliography\w*|caption)\*?'
                   r'(\[[^\]]*\])?\{[^}]*\}',
                   lambda m: ' ' if m.group(1) != 'caption' else ' ', p)
        # unwrap textual commands, drop the rest
        for _ in range(3):
            p = re.sub(r'\\(?:emph|textbf|textit|texttt|mbox|text|underline)'
                       r'\{([^{}]*)\}', r' \1 ', p)
        p = re.sub(r'\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?', ' ', p)
        p = re.sub(r'[{}~]', ' ', p)
        if len(p.split()) >= 5:
            out.append((line_no, p, emphs, keys))
    return out


def tokens_of(text):
    return re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*", text)


def analyze(name, files, window=1500):
    paras = []           # (fileshort, line, text, tokens)
    emph_terms, cite_seq = [], []
    for f in files:
        short = f.split('/')[-1]
        for line, p, emphs, keys in read_clean(f):
            paras.append((short, line, p, tokens_of(p)))
            emph_terms += emphs
            cite_seq.append((len(paras) - 1, keys))
    all_tokens = [t for _, _, _, tk in paras for t in tk]
    W = len([t for t in all_tokens if t not in ('MATHDISP', 'CITEMARK')])
    ndisp = sum(t == 'MATHDISP' for t in all_tokens)

    # ---- build concept vocabulary -------------------------------------
    vocab = {}   # normalized -> kind

    def add(term, kind):
        t = term.strip()
        if len(t) < 2 or t.lower() in STOP:
            return
        vocab.setdefault(t.lower(), kind)

    for _, _, _, tk in paras:
        prev = None
        for t in tk:
            if t in ('MATHDISP', 'CITEMARK'):
                prev = '.'; continue
            # A: acronym / mixed-case
            if (len(t) >= 2 and sum(c.isupper() for c in t) >= 2
                    and t not in ACRO_STOP and not t.isdigit()):
                add(t, 'acro')
            # B: mid-sentence capitalized word
            elif (t[0].isupper() and prev not in (None, '.')
                  and t not in CAP_STOP and len(t) > 2):
                add(t, 'proper')
            prev = t
    for e in emph_terms:
        add(e, 'emph')
    # E: recurring technical bigrams
    big = {}
    for _, _, _, tk in paras:
        low = [t.lower() for t in tk if t.isalpha()]
        for a, b in zip(low, low[1:]):
            if a in STOP or b in STOP or len(a) < 4 or len(b) < 4:
                continue
            big[(a, b)] = big.get((a, b), 0) + 1
    for (a, b), c in big.items():
        if c >= 4 and a not in vocab and f'{a} {b}' not in vocab:
            add(f'{a} {b}', 'bigram')
    # D: citation keys handled separately (positions known)

    # ---- occurrences via one-pass token index --------------------------
    def norm(t):
        t = t.lower()
        return t[:-2] if t.endswith("'s") else t

    offs, run = [], 0
    stream, orig, para_of = [], [], []   # normalized + original-case streams
    for i, (_, _, _, tk) in enumerate(paras):
        offs.append(run); run += len(tk)
        for t in tk:
            if t in ('MATHDISP', 'CITEMARK'):
                stream.append(None); orig.append(None); para_of.append(i)
            else:
                stream.append(norm(t)); orig.append(t); para_of.append(i)
    # fold possessive vocab variants and filter capitalized-ordinary-word
    # false positives: keep 'proper' terms only if they occur predominantly
    # capitalized in running text
    capcnt, lowcnt = {}, {}
    for t in orig:
        if t is None:
            continue
        n = norm(t)
        if t[0].isupper():
            capcnt[n] = capcnt.get(n, 0) + 1
        else:
            lowcnt[n] = lowcnt.get(n, 0) + 1
    vocab2 = {}
    for term, kind in vocab.items():
        t = norm(term)
        if kind == 'proper':
            c, l = capcnt.get(t, 0), lowcnt.get(t, 0)
            if c / max(c + l, 1) < 0.6:
                continue
        if t not in vocab2:
            vocab2[t] = kind
    vocab = vocab2
    uni, bi, tri = {}, {}, {}
    for j, t in enumerate(stream):
        if t is None:
            continue
        uni.setdefault(t, []).append(j)
        if j + 1 < len(stream) and stream[j + 1] is not None:
            bi.setdefault(t + ' ' + stream[j + 1], []).append(j)
            if j + 2 < len(stream) and stream[j + 2] is not None:
                tri.setdefault(' '.join(stream[j:j + 3]), []).append(j)
    intro = []           # (concept, kind, first_para, count, last_para)
    for term, kind in vocab.items():
        nw = term.count(' ') + 1
        pos = (uni if nw == 1 else bi if nw == 2 else tri).get(term, [])
        if nw > 3 or not pos:
            continue
        intro.append((term, kind, para_of[pos[0]], len(pos), para_of[pos[-1]]))
    for pi, keys in cite_seq:
        for k in keys:
            if k.lower() not in vocab:
                vocab[k.lower()] = 'cite'
                total = sum(kk == k for _, ks in cite_seq for kk in ks)
                lastp = max(p for p, ks in cite_seq if k in ks)
                intro.append((k, 'cite', pi, total, lastp))

    C = len(intro)
    counts = [c for _, _, _, c, _ in intro]
    spans = [max(0, offs[l] - offs[f]) for _, _, f, _, l in intro]
    per_para_new = [0] * len(paras)
    for _, _, f, _, _ in intro:
        per_para_new[f] += 1
    # live load: introductions inside trailing window
    intro_offsets = sorted(offs[f] for _, _, f, _, _ in intro)
    live = []
    import bisect
    for i in range(len(paras)):
        end = offs[i] + len(paras[i][3])
        lo = bisect.bisect_left(intro_offsets, end - window)
        hi = bisect.bisect_right(intro_offsets, end)
        live.append(hi - lo)
    burst = [(paras[i][0], paras[i][1], per_para_new[i],
              [t for t, _, f, _, _ in intro if f == i])
             for i in range(len(paras)) if per_para_new[i] >= 3]

    res = dict(name=name, W=W, C=C, paras=len(paras), ndisp=ndisp,
               rate=1000 * C / W, wpc=W / C,
               mean_occ=sum(counts) / C, med_occ=statistics.median(counts),
               singles=100 * sum(c == 1 for c in counts) / C,
               deep=100 * sum(c >= 5 for c in counts) / C,
               med_span=statistics.median(spans),
               burst_share=100 * len(burst) / len(paras),
               max_burst=max(per_para_new) if per_para_new else 0,
               live_mean=sum(live) / len(live),
               live_p95=sorted(live)[int(0.95 * len(live))],
               burst=sorted(burst, key=lambda x: -x[2]),
               intro=intro)
    return res


def show(rs):
    hdr = ('document                words  concepts  w/concept  intro/1000w  '
           'med.occ  single%  >=5occ%  burst-para%  live(mean/p95)')
    print(hdr); print('-' * len(hdr))
    for r in rs:
        print(f"{r['name']:22} {r['W']:6}  {r['C']:8}  {r['wpc']:9.0f}  "
              f"{r['rate']:11.1f}  {r['med_occ']:7.0f}  {r['singles']:6.0f}%  "
              f"{r['deep']:6.0f}%  {r['burst_share']:10.1f}%  "
              f"{r['live_mean']:5.1f}/{r['live_p95']}")


if __name__ == '__main__':
    results = []
    lint = None
    for arg in sys.argv[1:]:
        if arg.startswith('--lint='):
            lint = arg.split('=', 1)[1]; continue
        name, pats = arg.split(':', 1)
        files = sorted(sum((glob.glob(p) for p in pats.split(',')), []))
        results.append(analyze(name, files))
    show(results)
    if lint:
        r = next(x for x in results if x['name'] == lint)
        print(f"\nburst paragraphs in {lint} (>=3 new concepts):")
        for f, ln, n, terms in r['burst'][:15]:
            print(f"  {f}:{ln}  +{n}  {', '.join(terms[:8])}")
