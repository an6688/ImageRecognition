import unittest
from benchmarks.benchmark_folder import score,stats

class BenchmarkTests(unittest.TestCase):
    def test_category_presence_counts_misses_and_false_alarms(self):
        rows=[{'expected':['dog'],'predicted':['dog']},
              {'expected':['dog'],'predicted':[]},
              {'expected':[],'predicted':['cat']},
              {'expected':['cat'],'predicted':['cat']},
              {'expected':[],'predicted':[]}]
        result=score(rows)
        self.assertEqual(result['exact_match'],3)
        self.assertEqual(result['dog'],dict(tp=1,fp=0,fn=1,tn=3,precision=1,recall=.5))
        self.assertEqual(result['cat']['precision'],.5)
        self.assertEqual(result['cat']['recall'],1)

    def test_undefined_precision_is_not_reported_as_zero(self):
        result=score([{'expected':['dog'],'predicted':[]}])
        self.assertIsNone(result['dog']['precision'])
        self.assertEqual(result['dog']['recall'],0)
        self.assertIsNone(result['cat']['recall'])

    def test_timings_report_median_and_tail(self):
        result=stats([1,2,3,4,100])
        self.assertEqual(result['median'],3)
        self.assertGreater(result['p95'],4)

if __name__=='__main__':unittest.main()
