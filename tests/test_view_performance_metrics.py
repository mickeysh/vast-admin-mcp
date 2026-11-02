"""Tests for view performance metric selection and NaN-safe aggregation."""

import math
import unittest

from vast_admin_mcp.functions import (
    _filter_metrics_for_object_type,
    _normalize_metric_display,
    _process_performance_data,
    _format_performance_table,
)


class TestViewMetricFilter(unittest.TestCase):
    def test_selects_time_avg_bw_and_iops_not_rate(self):
        props = [
            'ViewMetrics,read_bw__rate',
            'ViewMetrics,read_bw__time_avg',
            'ViewMetrics,write_bw__time_avg',
            'ViewMetrics,read_iops__time_avg',
            'ViewMetrics,write_iops__time_avg',
            'ViewMetrics,read_md_iops__time_avg',
            'KafkaViewMetrics,view_fetch_event_value_bytes__rate',
            'ViewMetrics,rpc_get_fiber_latency__time_avg',
            'ViewMetrics,read_bw__sum_squares',
        ]
        filtered = _filter_metrics_for_object_type(props, 'view')
        self.assertIn('ViewMetrics,read_bw__time_avg', filtered)
        self.assertIn('ViewMetrics,write_bw__time_avg', filtered)
        self.assertIn('ViewMetrics,read_iops__time_avg', filtered)
        self.assertNotIn('ViewMetrics,read_bw__rate', filtered)
        self.assertNotIn('KafkaViewMetrics,view_fetch_event_value_bytes__rate', filtered)
        self.assertNotIn('ViewMetrics,rpc_get_fiber_latency__time_avg', filtered)
        self.assertNotIn('ViewMetrics,read_bw__sum_squares', filtered)

    def test_selects_latency_avg_not_rate_or_time_avg(self):
        props = [
            'ViewMetrics,read_latency__rate',
            'ViewMetrics,read_latency__avg',
            'ViewMetrics,write_latency__avg',
            'ViewMetrics,read_latency__time_avg',
            'ViewMetrics,read_md_latency__avg',
        ]
        filtered = _filter_metrics_for_object_type(props, 'view')
        self.assertEqual(
            sorted(filtered),
            sorted([
                'ViewMetrics,read_latency__avg',
                'ViewMetrics,write_latency__avg',
                'ViewMetrics,read_md_latency__avg',
            ]),
        )


class TestNormalizeDisplay(unittest.TestCase):
    def test_average_read_bandwidth_becomes_read_bw(self):
        name, units = _normalize_metric_display(
            'Average Read Bandwidth', 'MB/Sec', 'ViewMetrics,read_bw__time_avg'
        )
        self.assertEqual(name, 'Read')
        self.assertEqual(units, 'bw')

    def test_ms_latency_maps_to_latency_unit(self):
        name, units = _normalize_metric_display(
            'Average Read Latency', 'ms', 'ViewMetrics,read_latency__avg'
        )
        self.assertEqual(name, 'Read')
        # Values are microseconds despite catalog "ms"; formatter divides by 1000
        self.assertEqual(units, 'latency')

    def test_read_iops_title_merges_with_read(self):
        name, units = _normalize_metric_display(
            'Average READ IOPS', 'IOPS', 'ViewMetrics,read_iops__time_avg'
        )
        self.assertEqual(name, 'Read')
        self.assertEqual(units, 'iops')


class TestProcessPerformanceData(unittest.TestCase):
    def test_nan_columns_do_not_wipe_bandwidth(self):
        metrics = {
            'prop_list': [
                'timestamp',
                'object_id',
                'ViewMetrics,read_bw__time_avg',
                'KafkaViewMetrics,unused__time_avg',
            ],
            'object_ids': [4],
            'data': [
                [1, 4, 5_000_000_000.0, None],
                [2, 4, 6_000_000_000.0, None],
                [3, 4, 4_000_000_000.0, None],
            ],
        }
        metrics_map = {
            'view': {
                'ViewMetrics,read_bw__time_avg': {
                    'title': 'Average Read Bandwidth',
                    'units': 'MB/Sec',
                    'class_name': 'ViewMetrics',
                },
                'KafkaViewMetrics,unused__time_avg': {
                    'title': 'Unused',
                    'units': None,
                    'class_name': 'KafkaViewMetrics',
                },
            }
        }
        all_instances = [{'id': 4, 'name': 'view-4'}]
        table = _process_performance_data(metrics, metrics_map, 'view', all_instances)
        self.assertIn('view-4', table)
        self.assertIn('Read', table['view-4'])
        read_bw = table['view-4']['Read']['bw']
        self.assertAlmostEqual(read_bw['Max'], 6_000_000_000.0)
        self.assertAlmostEqual(read_bw['Average'], 5_000_000_000.0)
        # MB/Sec label must NOT trigger MiB rescale (values are already bytes/s)
        self.assertLess(read_bw['Max'], 7_000_000_000.0)

        formatted = _format_performance_table(table, 'view')
        read_row = next(r for r in formatted['view-4'] if r['Metric'] == 'Read')
        self.assertIn('GB/s', read_row['BW Max'])
        self.assertTrue(math.isclose(float(read_row['BW Max'].split()[0]), 6.0, rel_tol=0.05))


if __name__ == '__main__':
    unittest.main()
