"""APP-01 descriptive results and final evidence audit; no fitting."""
import ast
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import math
import tempfile
from copy import deepcopy
from verification import BASE,ROOT,read,successful,verify_all,verify_handoff,model,vector_values,require_families,verification_negative_controls
from studies import save

FAMILIES=('forecast','wallet','policy','nas','transport')

def binding(path):return {'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def summarize():
    outcomes=[]
    for name in FAMILIES:
        run=successful(name);summary=read(run/'results/summary.json');receipt=read(run/'receipt.json');methods={}
        for method in ('random','sobol','gp','tpe'):
            rows=[row for row in summary['rows'] if row['method']==method]
            methods[method]={'tuning_regrets':[r['tuning_regret'] for r in rows],'mean_tuning_regret':statistics.mean(r['tuning_regret'] for r in rows),'finite_minima_found':sum(abs(r['tuning_regret'])<=1e-10 for r in rows),'final_losses':[r['final_mean'] for r in rows],'mean_final_loss':statistics.mean(r['final_mean'] for r in rows),'search_seconds':sum(r['seconds'] for r in rows),'unique_proposals':[r['unique'] for r in rows]}
        grids=[read(run/'results'/str(rep)/'grid.json') for rep in (401,502,603)];grid_work=0
        for p in (run/'results').glob('*/grid/models/*.json'):grid_work+=read(p)['payload']['work']
        family_receipts=[read(p) for p in BASE.glob('*-'+name+'-*/receipt.json')]
        item={'name':name,'receipt':binding(run/'receipt.json'),'results':binding(run/'results/summary.json'),'grid_size':len(grids[0]['rows']),'grid_seconds':sum(g['seconds'] for g in grids),'grid_work_proxy':grid_work,'guarded_seconds':sum(r['seconds'] for r in family_receipts),'successful_guarded_seconds':receipt['seconds'],'attempts':len(family_receipts),'peak_rss_bytes':max(r['peak_rss_bytes'] for r in family_receipts),'output_bytes':sum(r['output_bytes'] for r in family_receipts),'methods':methods,'extra':summary['extra']}
        if name=='policy':
            from references import policy_truth,enumerate_value
            p,r=policy_truth();best=-float('inf');policies=[]
            for threshold,slope in itertools.product((-1.5,-.5,.5,1.5),(0.,.3)):
                acts=[[int(s>threshold+slope*t) for s in (-1.,0.,1.)] for t in range(3)];value=enumerate_value(p,r,acts);best=max(best,value);policies.append({'threshold':threshold,'time_slope':slope,'value':value})
            item['exact_policy_class']={'policies':policies,'best_value':best,'selected':[{ 'replicate':row['replicate'],'method':row['method'],'true_value':row['final_metrics'][0]['true_value'],'class_regret':best-row['final_metrics'][0]['true_value'],'unrestricted_markov_regret':row['final_metrics'][0]['policy_regret']} for row in summary['rows']]}
        if name=='nas':
            item['vector']=[]
            for rep,grid in zip((401,502,603),grids):
                vector=read(run/'results'/str(rep)/'vector/result.json');finite_feasible=sum(vector_values([model(p) for p in row['artifacts']])[2] for row in grid['rows'])
                finals=vector['evaluation']['final']
                item['vector'].append({'replicate':rep,'grid_feasible_configurations':finite_feasible,'front_size':len(vector['front']),'final_records':len(finals),'feasible_final_records':sum(row['feasible'] for row in finals),'outcome':vector['reason']})
        if name=='transport':
            pairs=[]
            for rep in (401,502,603):
                for method in ('random','sobol','gp','tpe'):
                    handoff=read(run/'results'/str(rep)/method/'handoff.json')
                    for candidate in handoff['candidates']:
                        if candidate['status']!='verified':continue
                        assessment=candidate['posterior']['assessment'];chains=candidate['posterior']['chains']
                        pairs.append({'replicate':rep,'method':method,'step_size':candidate['step_size'],'length':candidate['leapfrog_steps'],'mean_error_max':max(abs(x) for x in assessment['mean']),'second_moment_error_max':max(abs(x-y) for x,y in zip(assessment['second_moment'],assessment['true_second_moment'])),'acceptance':statistics.mean(float(r['accepted']) for c in chains for r in c['records'])})
            item['sampling_assessment']={'verified_pairs':len(pairs),'transitions':len(pairs)*2*160,'retained_draws':len(pairs)*2*128,'max_mean_error':max(p['mean_error_max'] for p in pairs),'max_second_moment_error':max(p['second_moment_error_max'] for p in pairs),'pairs':pairs,'convergence_claim':False,'used_for_selection':False}
        outcomes.append(item)
    return {'families':outcomes,'total_guarded_seconds':sum(r['guarded_seconds'] for r in outcomes),'scalar_studies':60,'replicates':3,'search_budget':16,'statistical_claim':'descriptive finite replication only; no superiority or power claim'}

def synthesize(out):
    result=summarize();save(out/'results.json',result);lines=['# APP-01 five-family application validation results','','These are independent stylized companions inspired by workspace contracts. They use no sibling imports, data, environments or services. Scientific source qualification remains separate from these bounded application results.','','## Execution summary','','| Family | Grid configurations | Guarded seconds | Grid seconds | Peak RSS MiB |','|---|---:|---:|---:|---:|']
    for item in result['families']:lines.append('| '+item['name']+' | '+str(item['grid_size'])+' | '+format(item['guarded_seconds'],'.2f')+' | '+format(item['grid_seconds'],'.2f')+' | '+format(item['peak_rss_bytes']/2**20,'.1f')+' |')
    lines+=['','60 scalar studies: five families, three fixed data replicates and four search methods, 16 proposals each. Every family also retains exhaustive reference fitting, fresh final fits and an interrupted/resumed random study. NAS adds three constrained vector studies and a separate promoted momentum-SGD recovery comparison. Reference work is additional; neither grid nor recovery cost is hidden in the search budget.','','## Finite optimizer comparison','','Losses have different units across families and must not be pooled. Tuning regret is best observed tuning loss minus the complete finite grid minimum with identical data and initializations. Final losses are protected evaluations of newly refitted models.','','| Family | Method | Mean tuning regret | Exact finite minima / 3 | Mean final loss | Search seconds |','|---|---|---:|---:|---:|---:|']
    for item in result['families']:
        for method,m in item['methods'].items():lines.append('| '+item['name']+' | '+method+' | '+format(m['mean_tuning_regret'],'.6g')+' | '+str(m['finite_minima_found'])+' | '+format(m['mean_final_loss'],'.6g')+' | '+format(m['search_seconds'],'.2f')+' |')
    lines+=['','## Models and independent checks','','### Forecasting','The latent process is AR(1), rho=0.6 and Q=0.15. The observed signal has known lagged exogenous and delayed auxiliary covariates plus latent state and Gaussian noise. Candidate lag, ridge and observation variance are statistical model choices. Regression uses observed training rows only; the filter conditions on observations only after their availability time. Selected fits refit on train+validation. An independently assembled joint Gaussian covariance gives the same conditional likelihood as recursive filtering; an augmented least-squares solve checks ridge coefficients. This fixture has sparse delayed observations, not a full macroeconomic mixed-frequency system.','','### Censored wallets','Z=0.3+0.7x-0.2x^2+0.6 epsilon; W=max(exp(Z)-1,0). The zero mass is Phi(-mu/sigma); positive observations use a lognormal density with its Jacobian. Feature degree, ridge and fixed sigma form the finite domain. Scalar formulas, independent stationarity residuals and numerical quadrature verify likelihood and expected external wallet. The fixed-sigma coefficient problem is convex. Positive fitting regularization means the fitted optimum need not equal the generating parameters.','','### Sequential policy selection','Three states, two actions, three periods and known logging probabilities form a controlled process. Threshold and time-slope policies are evaluated using a doubly robust estimator with train-only fitted transition/reward models and independent validation trajectories. Smoothing is an estimator hyperparameter. Independent enumeration of all state paths checks policy values. The unrestricted Markov optimum and best declared threshold class are separate references. Missing overlap and role leakage refuse explicitly. Final noisy estimates are not identified with exact policy values.','','### Constrained NAS','Networks learn exp(-a*x) and both derivatives. Width, depth, activation and learning rate change actual trained models. Scalar comparisons use the sum of three validation MSEs. The vector workflow retains value-error/parameter-count fronts under separate maximum derivative constraints. Limits are frozen from an interpolation resolution h=0.25 and curvature bounds: h*0.6^2*exp(0.3) and h*0.5^2*exp(0.3). These are a declared numerical resolution target, not a universal financial materiality standard. Learned-model nonattainment is retained. The separate streaming test serializes weights and momentum through 40/120 updates and verifies interrupted trajectories against uninterrupted execution.','','### Neural transport','The target is X1=Z1, X2=Z2+0.35(Z1^2-1), with iid Gaussian Z. Trained triangular maps T(z)=(z1,exp(s)*z2+MLP(z1)) have explicit inverse and Jacobian. Held-out model likelihood selects architecture; fresh final training precedes freezing. HMC uses the exact target pulled back through the frozen map. Every candidate gets development and fresh reversibility/volume/gradient checks; all passing pairs remain. Short retained chains have exact-target mean/second-moment discrepancies reported separately. A verified map or candidate is not a convergence certificate.','','## Findings and limitations','','The tables retain adverse and null findings. Finding a finite tuning optimum does not imply the best final score. Tiny numerical models can make complete enumeration faster than Bayesian optimization. Duplicate proposals are paid; deterministic repeats provide orchestration coverage rather than additional statistical precision. TPE retains its ten default startup trials and has only six potentially adaptive proposals. Ordinal encoding of categorical choices is explicit and may affect search behavior. Work units are documented proxies, not currency or hardware FLOPs. No production, real-bank, distributed-host or universal optimizer claim follows.','','## Reproduction and authority','','Use exact commands in docs/PROGRAM_OPERATIONS.md. Each command verifies the reviewed input manifest, preserves an immutable result directory, enforces CPU/time/RSS/disk/output bounds, and records source/runtime identity. Successful family allocations cannot rerun automatically. The live master and program.json own dependencies and status; the final APP-01 review precedes GAP-01/FINAL-AUDIT.']
    detail=['','## Observed scientific outcomes','','### Constrained feasibility','','| Replicate | Feasible grid configurations / 24 | Tuning front | Feasible final fits | Terminal outcome |','|---|---:|---:|---:|---|']
    nas=next(x for x in result['families'] if x['name']=='nas')
    for row in nas['vector']:detail.append('| '+str(row['replicate'])+' | '+str(row['grid_feasible_configurations'])+' | '+str(row['front_size'])+' | '+str(row['feasible_final_records'])+' | '+row['outcome']+' |')
    detail+=['','No constrained NAS result passes protected final evaluation. For replicates 401 and 502, the exhaustive declared grid itself has no feasible configuration under the frozen training budget. Replicate 603 has two feasible grid configurations and one search-front model, but its fresh final fit is infeasible. These are scientific nonattainment results, not execution failures. Enlarging training or changing architecture is a future program amendment, not an unreported relaxation of this test.']
    transport=next(x for x in result['families'] if x['name']=='transport')['sampling_assessment']
    detail+=['','### Sampler verification and finite discrepancies','',str(transport['verified_pairs'])+' map/sampler pairs pass the finite numerical checks; '+str(transport['transitions'])+' transitions are independently replayed. Maximum absolute mean discrepancy is '+format(transport['max_mean_error'],'.6g')+' and maximum second-moment discrepancy is '+format(transport['max_second_moment_error'],'.6g')+'. Short trajectories can therefore have substantial sampling error despite mechanically correct HMC. These diagnostics do not rank candidates or establish convergence.','','### Accounting and scope','','Total guarded family-operation time, including failed NAS attempts and recovery continuations: '+format(result['total_guarded_seconds'],'.2f')+' seconds. This excludes separate controls, reconstruction, reporting and governance operations. Three data replicates provide descriptive comparisons only. The existing LaTeX manual is the accepted predecessor; this extension is documented by this report, README.md, the five-problem master and immutable evidence.']
    position=lines.index('## Findings and limitations');lines[position:position]=detail+['']
    content=chr(10).join(lines)+chr(10);(out/'RESULTS.md').write_text(content);(ROOT/'hpo-survey/applications/RESULTS.md').write_text(content);return result

def audit(out):
    result=verify_all()
    require_families(result['families']);negative=verification_negative_controls()
    p=read(ROOT/'docs/program/program.json');steps={s['id']:s for s in p['continuation']['steps']};required=['DESIGN','REFERENCES','FORECAST','WALLET','POLICY','NAS','TRANSPORT','SYNTHESIS']
    if any(steps['APP-01/'+x]['state']!='complete' for x in required):raise AssertionError('Incomplete APP stage')
    if steps['APP-01/FINAL-REVIEW']['state']!='in_progress':raise AssertionError('Final review not active')
    if p['continuation']['steps'][-1]['id']!='GAP-01/FINAL-AUDIT' or 'APP-01/FINAL-REVIEW' not in steps['GAP-01/FINAL-AUDIT']['dependencies']:raise AssertionError('Terminal audit can bypass extension')
    for row in p['evidence']+p['source_inputs']:
        if binding(ROOT/row['path'])['sha256']!=row['sha256']:raise AssertionError('Changed registered evidence: '+row['path'])
    source_index={};retained=BASE/'source-versions'
    for path in retained.glob('*.txt'):source_index[hashlib.sha256(path.read_bytes()).hexdigest()]=path
    manifests={hashlib.sha256(path.read_bytes()).hexdigest():path for path in BASE.glob('manifest-[0-9]*.json')}
    intents=[];incomplete=[]
    for path in sorted(BASE.glob('*/intent.json')):
        intent=read(path)
        if intent['manifest']['sha256'] not in manifests:raise AssertionError('Consumed numbered manifest lost')
        if read(manifests[intent['manifest']['sha256']])['inputs']!=intent['inputs']:raise AssertionError('Intent inputs differ from frozen manifest')
        for row in intent['inputs']:
            current=ROOT/row['path']
            if (not current.exists() or hashlib.sha256(current.read_bytes()).hexdigest()!=row['sha256']) and row['sha256'] not in source_index:raise AssertionError('Failed-attempt source version lost')
        intents.append(binding(path))
        if not (path.parent/'receipt.json').exists():
            if path.parent==out:continue
            if path.parent.name!='20261024T125012Z-controls-05f81073' or not (path.parent/'execution.log').exists():raise AssertionError('Unresolved operation without receipt')
            incomplete.append({'intent':binding(path),'log':binding(path.parent/'execution.log'),'disposition':'Initial receipt-writer failure retained as unsuccessful; superseded by successful controls. No retrospective receipt fabricated.'})
    receipts=[]
    for path in sorted(BASE.glob('*/receipt.json')):
        receipt=read(path)
        if receipt['manifest']['sha256'] not in manifests:raise AssertionError('Receipt manifest lost')
        for row in receipt.get('inputs',[]):
            current=ROOT/row['path']
            if not current.exists() or hashlib.sha256(current.read_bytes()).hexdigest()!=row['sha256']:
                if row['sha256'] not in source_index:raise AssertionError('Consumed source version lost')
        if receipt.get('log') and binding(ROOT/receipt['log']['path'])!=receipt['log']:raise AssertionError('Changed run log')
        receipts.append(binding(path))
    control_runs=[path.parent for path in BASE.glob('*-controls-*/receipt.json') if read(path)['passed']]
    if not control_runs:raise AssertionError('Missing passing controls')
    controls=read(sorted(control_runs)[-1]/'controls.json')
    if not controls['passed'] or not set(negative['rejected']).issubset(controls['checks']):raise AssertionError('Latest controls omit audit negative tests')
    synthesis=successful('synthesis');expected=summarize()
    if read(synthesis/'results.json')!=expected:raise AssertionError('Synthesis differs from source artifacts')
    if (synthesis/'RESULTS.md').read_bytes()!=(ROOT/'hpo-survey/applications/RESULTS.md').read_bytes():raise AssertionError('Published result view differs')
    handoff=read(successful('transport')/'results/401/random/handoff.json');tamper_checks=[]
    with tempfile.TemporaryDirectory(prefix='app01-audit-negative-') as temp:
        mutations=[]
        missing=deepcopy(handoff);missing['candidates'].pop();mutations.append(('omitted sampler candidate',missing))
        volume=deepcopy(handoff);volume['candidates'][0]['fresh'][0]['volume']+=.1;mutations.append(('altered fresh volume check',volume))
        acceptance=deepcopy(handoff);acceptance['candidates'][0]['posterior']['chains'][0]['records'][0]['loga']+=.1;mutations.append(('altered HMC acceptance',acceptance))
        for index,(name,record) in enumerate(mutations):
            target=Path(temp)/(str(index)+'.json');save(target,record)
            try:verify_handoff(target)
            except AssertionError:tamper_checks.append(name)
            else:raise AssertionError('Tampered artifact accepted: '+name)
    for name in FAMILIES:
        receipt=read(successful(name)/'receipt.json')
        if not receipt['inputs_unchanged'] or receipt['source_digest']!='7a3975382cf19d55d3be3b653ccf5f860c576e13e7998a9dded47dff0a9adb17':raise AssertionError('Scientific core changed')
    for path in (ROOT/'hpo-survey/applications').glob('*.py'):
        tree=ast.parse(path.read_text());imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.extend(n.name for n in node.names)
            if isinstance(node,ast.ImportFrom):imports.append(node.module or '')
        if any(name.split('.')[0] in {'bayesfilter','sme_wallet','causalbank','mooneural','finmarketing','dsge_hmc'} for name in imports):raise AssertionError('Sibling import')
    artifacts=[binding(path) for name in FAMILIES for path in sorted((successful(name)/'results').rglob('*')) if path.is_file()]
    output={'passed':True,'reviewed_revision':p['revision'],'families':result['families'],'scalar_studies':sum(x['scalar_studies'] for x in result['families']),'vector_studies':sum(x['vector_studies'] for x in result['families']),'models_reconstructed':sum(x['models_reconstructed'] for x in result['families']),'hmc_transitions_replayed':sum(x['hmc_transitions_replayed'] for x in result['families']),'receipts':receipts,'artifacts':artifacts,'unresolved_required_mechanics':[],'limits':['Finite application evidence, not bank effectiveness','Three replicates; no superiority or power claim','Short HMC runs do not prove posterior convergence','Separate-machine testing remains waived'],'next_stage':'GAP-01/FINAL-AUDIT'}
    output.update(negative_controls=negative,artifact_tamper_controls=tamper_checks,intents=intents,incomplete_initial_attempts=incomplete,numbered_manifests=[binding(path) for path in manifests.values()],controls=binding(sorted(control_runs)[-1]/'controls.json'),synthesis=binding(synthesis/'results.json'),scientific_nonattainment=next(x for x in expected['families'] if x['name']=='nas')['vector'])
    save(out/'audit.json',output);return output
