import unittest

from research.shared_stock_context import SharedStockContext,model

T=1791000000


class ContextTests(unittest.TestCase):
    def test_future_rows_and_target_item_never_change_past_context(self):
        prefix=[model.OBS(T,100,'a'),model.OBS(T+600,50,'a')]
        series={f'x:Peer {i} Plushie':prefix for i in range(8)}
        a=SharedStockContext(series,lambda a,b:False).at(T+600,'target')
        changed={k:rows+[model.OBS(T+900,9999,'b')] for k,rows in series.items()}
        changed['target']=[model.OBS(T,0,'c')]
        b=SharedStockContext(changed,lambda a,b:False).at(T+600,'target')
        self.assertEqual(a,b)
        # Exclusion works for an actual plushie target, not only a missing key.
        target='x:Peer 0 Plushie';changed[target]=[model.OBS(T,0,'c')]
        self.assertEqual(SharedStockContext(series,lambda a,b:False).at(T+600,target),
                         SharedStockContext(changed,lambda a,b:False).at(T+600,target))
        self.assertEqual(a[2],2.)

    def test_topups_and_provider_switches_cannot_masquerade_as_consumption(self):
        for mode in ('topup','provider'):
            rows=[model.OBS(T,100,'a'),model.OBS(T+300,200 if mode=='topup' else 75,'a'),
                  model.OBS(T+600,50,'b' if mode=='provider' else 'a')]
            c=SharedStockContext({f'x:Peer {i} Plushie':rows for i in range(8)},lambda a,b:False)
            self.assertEqual(c.at(T+600,'target')[2],0.)

    def test_missing_peer_evidence_and_active_gaps_do_not_invent_regime(self):
        rows=[model.OBS(T,100,'a')]
        series={f'x:Peer {i} Plushie':rows for i in range(6)}
        self.assertIsNone(SharedStockContext(series,lambda a,b:False).at(T,'x:Peer 0 Plushie'))
        self.assertIsNone(SharedStockContext(series,lambda a,b:False).at(T+86401,'target'))
        self.assertIsNone(SharedStockContext(series,lambda a,b:True).at(T,'target'))

    def test_lifetime_context_closes_at_zero_not_residual_stock(self):
        import math
        rows=[model.OBS(T,0,'a')]
        for i in range(3):
            rows.extend([model.OBS(T+100+i*300,100,'a'),model.OBS(T+150+i*300,20,'a'),
                         model.OBS(T+200+i*300,0,'a')])
        rows.extend([model.OBS(T+1000,100,'a'),model.OBS(T+1100,20,'a'),model.OBS(T+1200,0,'a')])
        c=SharedStockContext({f'x:Peer {i} Plushie':rows for i in range(8)},lambda a,b:False)
        self.assertEqual(c.at(T+1150,'target')[-1],0.)
        self.assertAlmostEqual(c.at(T+1200,'target')[-1],math.log(2.))
        self.assertTrue(all(epoch==T+1200 for epoch,_,_ in c.events))


if __name__=='__main__':unittest.main()
