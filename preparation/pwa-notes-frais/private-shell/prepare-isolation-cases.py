#!/usr/bin/env python3
"""Generate an offline execution worklist. No HTTP client, cookies or execution mode."""
import argparse
import json
from pathlib import Path

P=Path(__file__).resolve().parent


def prepare(data):
    families={f['id']:f for f in data['sessionFamilies']}
    expected={(family,axis) for family in families for axis in data['sessionAxes']}
    observed={(c['family'],c['axis']) for c in data['sessionCases']}
    if observed!=expected or len(data['sessionCases'])!=len(expected):
        raise ValueError('Isolation matrix incomplete or duplicated')
    for row in data['sessionCases']:
        if row['status']!='NON_EXECUTE' or row.get('proofSha256') or row.get('returnCode') is not None:
            raise ValueError('Worklist cannot convert results into planned checks')
        family=families[row['family']]
        yield {'id':row['id'],'method':family['method'],'pathTemplate':family['path'],
               'variant':family['variant'],'axis':row['axis'],'status':'NON_EXECUTE',
               'applicability':'A_CONFIRMER','requiredFixtures':['synthetic-account-context','valid-positive-payload',
                    'existing-authorized-note-and-attachment','existing-foreign-note-and-attachment'],
               'executionSteps':['resolve-private-fixture-mapping','verify-positive-same-method-and-workflow',
                    'authorize-gate-session-if-mutating','replay-negative-with-single-context-change',
                    'classify-gate-versus-backend-response','compare-before-after-data-and-hashes'],
               'result':{'returnCode':None,'httpStatus':None,'refusalOrigin':None,'beforeHash':None,
                         'afterHash':None,'proofSha256':None,'reviewer':None},
               'blockedBy':['no-preprod-authorization','fixtures-and-role-contract-not-confirmed']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    matrix=json.loads((P/'MATRICE-CORRECTIONS-PREPROD.json').read_text())
    # Never overwrite proof/result files; output contains templates only.
    with args.output.open('x',encoding='utf-8') as stream:
        args.output.chmod(0o600)
        for case in prepare(matrix):stream.write(json.dumps(case,ensure_ascii=False)+'\n')
