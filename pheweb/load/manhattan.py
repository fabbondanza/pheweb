
'''
This script creates json files which can be used to render Manhattan plots.
'''

# NOTE: `qval` means `-log10(pvalue)`

# TODO: optimize binning for fold@20 view.
#       - if we knew the max_qval before we started (eg, by running qq first), it would be very easy.
#       - at present, we set qval bin size well for the [0-40] range but not for variants above that.
# TODO: combine with QQ?

from ..utils import chrom_order
from ..conf_utils import conf
from ..file_utils import VariantFileReader, write_json, common_filepaths
from .load_utils import MaxPriorityQueue, parallelize_per_pheno

import math

BIN_LENGTH = int(3e6)


def run(argv):
    if '-h' in argv or '--help' in argv:
        print('Make a Manhattan plot for each phenotype.')
        exit(1)

    if '--from-gz' in argv:
        parallelize_per_pheno(
            get_input_filepaths = lambda pheno: common_filepaths['pheno_gz'](pheno['phenocode']),
            get_output_filepaths = lambda pheno: common_filepaths['manhattan'](pheno['phenocode']),
            convert = make_manhattan_json_file_from_gz,
            cmd = 'manhattan',
        )
    else:
        parallelize_per_pheno(
            get_input_filepaths = lambda pheno: common_filepaths['pheno'](pheno['phenocode']),
            get_output_filepaths = lambda pheno: common_filepaths['manhattan'](pheno['phenocode']),
            convert = make_manhattan_json_file,
            cmd = 'manhattan',
        )


def make_manhattan_json_file_from_gz(pheno):
    make_manhattan_json_file_explicit(common_filepaths['pheno_gz'](pheno['phenocode']),
                                      common_filepaths['manhattan'](pheno['phenocode']))
def make_manhattan_json_file(pheno):
    make_manhattan_json_file_explicit(common_filepaths['pheno'](pheno['phenocode']),
                                      common_filepaths['manhattan'](pheno['phenocode']))
def make_manhattan_json_file_explicit(in_filepath, out_filepath):
    binner = Binner()
    with VariantFileReader(in_filepath) as variants:
        for variant in variants:
            binner.process_variant(variant)
    data = binner.get_result()
    write_json(filepath=out_filepath, data=data)


class Binner:
    def __init__(self):
        self._peak_best_variant = None
        self._peak_last_chrpos = None
        self._peak_pq = MaxPriorityQueue()
        self._unbinned_variant_pq = MaxPriorityQueue()
        self._bins = {} # like {<chrom>: {<pos // bin_length>: [{chrom, startpos, qvals}]}}
        self._qval_bin_size = 0.05 # this makes 200 bins for the minimum-allowed y-axis covering 0-10

    def process_variant(self, variant):
        '''
        There are 3 types of variants:
          a) If the variant starts or extends a peak and has a stronger pval than the current `peak_best_variant`:
             1) push the old `peak_best_variant` into `unbinned_variant_pq`.
             2) make the current variant the new `peak_best_variant`.
          b) If the variant ends a peak, push `peak_best_variant` into `peak_pq` and push the current variant into `unbinned_variant_pq`.
          c) Otherwise, just push the variant into `unbinned_variant_pq`.
        Whenever `peak_pq` exceeds the size `conf.manhattan_peak_max_count`, push its member with the weakest pval into `unbinned_variant_pq`.
        Whenever `unbinned_variant_pq` exceeds the size `conf.manhattan_num_unbinned`, bin its member with the weakest pval.
        So, at the end, we'll have `peak_pq`, `unbinned_variant_pq`, and `bins`.
        '''

        if variant['pval'] != 0:
            qval = -math.log10(variant['pval'])
            if qval > 40:
                self._qval_bin_size = 0.2 # this makes 200 bins for a y-axis extending past 40 (but folded so that the lower half is 0-20)
            elif qval > 20:
                self._qval_bin_size = 0.1 # this makes 200-400 bins for a y-axis extending up to 20-40.

        if variant['pval'] < conf.manhattan_peak_pval_threshold: # part of a peak
            if self._peak_best_variant is None: # open a new peak
                self._peak_best_variant = variant
                self._peak_last_chrpos = (variant['chrom'], variant['pos'])
            elif self._peak_last_chrpos[0] == variant['chrom'] and self._peak_last_chrpos[1] + conf.manhattan_peak_sprawl_dist > variant['pos']: # extend current peak
                self._peak_last_chrpos = (variant['chrom'], variant['pos'])
                if variant['pval'] >= self._peak_best_variant['pval']:
                    self._maybe_bin_variant(variant)
                else:
                    self._maybe_bin_variant(self._peak_best_variant)
                    self._peak_best_variant = variant
            else: # close old peak and open new peak
                self._maybe_peak_variant(self._peak_best_variant)
                self._peak_best_variant = variant
                self._peak_last_chrpos = (variant['chrom'], variant['pos'])
        else:
            self._maybe_bin_variant(variant)

    def _maybe_peak_variant(self, variant):
        self._peak_pq.add_and_keep_size(variant, variant['pval'],
                                        size=conf.manhattan_peak_max_count,
                                        popped_callback=self._maybe_bin_variant)
    def _maybe_bin_variant(self, variant):
        self._unbinned_variant_pq.add_and_keep_size(variant, variant['pval'],
                                                    size=conf.manhattan_num_unbinned,
                                                    popped_callback=self._bin_variant)
    def _bin_variant(self, variant):
        chrom_idx = chrom_order[variant['chrom']]
        if chrom_idx not in self._bins: self._bins[chrom_idx] = {}
        pos_bin_id = variant['pos'] // BIN_LENGTH
        if pos_bin_id not in self._bins[chrom_idx]:
            self._bins[chrom_idx][pos_bin_id] = {'chrom': variant['chrom'], 'startpos': pos_bin_id * BIN_LENGTH, 'qvals': set()}
        qval = self._rounded(-math.log10(variant['pval']))
        self._bins[chrom_idx][pos_bin_id]["qvals"].add(qval)

    def get_result(self):
        self.get_result = None # this can only be called once

        if self._peak_best_variant:
            self._maybe_peak_variant(self._peak_best_variant)

        peaks = list(self._peak_pq.pop_all())
        for peak in peaks: peak['peak'] = True
        unbinned_variants = list(self._unbinned_variant_pq.pop_all())
        unbinned_variants = sorted(unbinned_variants + peaks, key=(lambda variant: variant['pval']))

        # unroll dict-of-dict-of-array `bins` into array `variant_bins`
        variant_bins = []
        for chrom_idx in sorted(self._bins.keys()):
            for pos_bin_id in sorted(self._bins[chrom_idx].keys()):
                b = self._bins[chrom_idx][pos_bin_id]
                assert len(b['qvals']) > 0
                b['qvals'], b['qval_extents'] = self._get_qvals_and_qval_extents(b['qvals'])
                b['pos'] = int(b['startpos'] + BIN_LENGTH/2)
                del b['startpos']
                variant_bins.append(b)

        return {
            'variant_bins': variant_bins,
            'unbinned_variants': unbinned_variants,
        }

    def _rounded(self, qval):
        # round down to the nearest multiple of `self._qval_bin_size`, then add 1/2 of `self._qval_bin_size` to be in the middle of the bin
        x = qval // self._qval_bin_size * self._qval_bin_size + self._qval_bin_size / 2
        return round(x, 3) # trim `0.35000000000000003` to `0.35` for convenience and network request size

    def _get_qvals_and_qval_extents(self, qvals):
        qvals = sorted(self._rounded(qval) for qval in qvals)
        extents = [[qvals[0], qvals[0]]]
        for q in qvals:
            if q <= extents[-1][1] + self._qval_bin_size * 1.1:
                extents[-1][1] = q
            else:
                extents.append([q,q])
        rv_qvals, rv_qval_extents = [], []
        for (start, end) in extents:
            if start == end:
                rv_qvals.append(start)
            else:
                rv_qval_extents.append([start,end])
        return (rv_qvals, rv_qval_extents)
