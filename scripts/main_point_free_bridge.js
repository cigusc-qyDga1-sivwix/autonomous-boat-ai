#!/usr/bin/env node
'use strict';
const fs=require('node:fs');
const old=require('./main_four_factor_bridge.js');
const engine=globalThis.BoatTacticalModel;
const MODEL='four-factor-v1.5-point-free-untrained';
function validBets(bets){return Array.isArray(bets)&&bets.length>=1&&bets.length<=120&&
 new Set(bets.map(b=>b.combination)).size===bets.length&&bets.every(b=>
 /^[1-6]-[1-6]-[1-6]$/.test(b.combination)&&new Set(b.combination.split('-')).size===3&&
 Number.isSafeInteger(b.virtual_yen)&&b.virtual_yen>=100&&b.virtual_yen%100===0)&&
 bets.reduce((n,b)=>n+b.virtual_yen,0)===50000;}
function run(input){
 // The existing adapter validates six racers/source timestamp and preserves all
 // venue controls. Edogawa remains excluded from venue-tactics adjustments.
 const control=old.run({...input,venue_tactics_trial:input.venue!=='江戸川',
  postrace_conditional_trial:input.venue==='江戸川',head_coverage_trial:false});
 const result=engine.forecastFourFactorPointFree(input);
 if(result.model!==MODEL||!validBets(result.bets)||
    result.metadata.four_factor.ticket_policy?.version!=='point-free-v1.5')throw Error('Invalid point-free result');
 const policy=result.metadata.four_factor.ticket_policy;
 if(policy.candidates.length!==120||policy.selected_count!==result.bets.length)throw Error('Missing selection provenance');
 return {...control,model_version:MODEL,bets:result.bets,
  four_factor:result.metadata.four_factor,head_course_shares:result.head_course_shares,
  role_coverage:result.role_coverage,role_changes:result.role_changes,
  postrace_conditional_v13:result.metadata.postrace_v13,
  // Prior ablations refer to the predecessor; clear them rather than
  // claiming they compare v1.5 predictions.
  venue_tactics_ab:null,venue_surface_ab:null,postrace_conditional_control:null,
  point_free_control:{model_version:control.model_version,bets:control.bets,
    frozen_at_utc:input.frozen_at_utc,generated_pre_cutoff:true,
    model_role:'shadow_validation',scope:'Same input scores; predecessor selection and allocation; no extra formal stake'},
  point_free_provenance:{version:'point-free-v1.5',result_data_used:false,odds_used:false,
   pre_cutoff_only:true,score_model_unchanged:true,selection_and_allocation_changed:true,
   trajectory_learning_completed:false}};
}
module.exports={run,validBets,MODEL};
if(require.main===module){try{process.stdout.write(JSON.stringify(run(JSON.parse(fs.readFileSync(0,'utf8'))))+'\n');}
catch(e){process.stderr.write('MAIN_POINT_FREE_BRIDGE: '+String(e?.message||e)+'\n');process.exitCode=1;}}
