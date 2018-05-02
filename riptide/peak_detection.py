import warnings
import operator

##### Non-standard imports #####
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import pandas

##### Local imports #####
from .clustering import cluster_1d

# NOTE: the spacing of FFA period trials in frequency space is nearly constant
# Variations in spacing are mostly caused by the discrete downsampling steps

# NOTE: one segment should cover at the very least 1 DFT bin worth of trials.
# This is to ensure some level of
# statistical independence between consecutive bins
# 10 DFT bins or more seems much better
def segment(periods, tobs, segment_dftbins_length=10.0):
    """ Break the period trials array into equal-sized segments, returning
    their boundaries and other information as a pandas.DataFrame
    """
    # Number of DFT bin indexes spanned by the period trials
    dbi_range = tobs / periods[0] - tobs / periods[-1]

    # Number of segments, enforce it to be at least 1
    nseg = max(1, int(dbi_range / segment_dftbins_length))
    slen = len(periods) // nseg

    boundaries = [
        (iseg * slen, (iseg + 1) * slen)
        for iseg in range(nseg)
        ]

    # Last segment must end at the last period trial
    last = boundaries[-1]
    boundaries[-1] = (last[0], len(periods))
    boundaries = np.asarray(boundaries)

    data = pandas.DataFrame(
        columns=['istart', 'iend', 'imid', 'pmid', 'logpmid']
        )
    data['istart'] = boundaries[:, 0]
    data['iend'] = boundaries[:, 1]
    data['imid'] = (data['istart'] + data['iend']) // 2

    # The .values is to avoid a warning where data['imid'] seems to be perceived
    # as non-integer when using it to index the periods array.
    data['pmid'] = periods[data['imid'].values]
    data['logpmid'] = np.log(data['pmid'])
    return data

def segment_stats(snrs, boundaries):
    """ Compute the median and robust standard deviation of each Periodogram
    segment. """
    percentiles = (25, 50, 75)
    stats = pandas.DataFrame(
        [ np.percentile(snrs[s:e], percentiles) for s, e in boundaries[['istart', 'iend']].as_matrix() ],
        columns=['p25', 'median', 'p75']
        )
    stats['sigma'] = (stats['p75'] - stats['p25']) / 1.349
    stats['pmid'] = boundaries['pmid']
    stats['logpmid'] = boundaries['logpmid']
    return stats


# NOTE: threshold will be a 2nd degree polynomial function of x = log(period)
# This function returns the polynomial coefficients in x
def threshold_function_dynamic(stats, snr_min=6.5, nsigma=6.5, polydeg=2):
    x = stats['logpmid']
    y = stats['median'] + nsigma * stats['sigma']
    poly = np.poly1d( np.polyfit(x, y, polydeg) )
    def func(period):
        return np.maximum(poly(np.log(period)), snr_min)
    return func, poly.coefficients

def threshold_function_static(snr_min, polydeg=2):
    def func(period):
        thr = np.empty(len(period))
        thr.fill(snr_min)
        return thr
    polyco = np.zeros(polydeg + 1)
    return func, polyco


class Peak(object):
    """ """
    def __init__(self, period, snr, dm, iw, width, ducy):
        self._period = period
        self._snr = snr
        self._width = width
        self._iw = iw
        self._dm = dm
        self._ducy = ducy

    @property
    def period(self):
        return self._period

    @property
    def freq(self):
        return 1.0 / self.period

    @property
    def snr(self):
        return self._snr

    @property
    def width(self):
        return self._width

    @property
    def iw(self):
        """ Best trial width index. """
        return self._iw

    @property
    def dm(self):
        return self._dm

    @property
    def ducy(self):
        """ Best duty cycle """
        return self._ducy

    def __str__(self):
        name = type(self).__name__
        dm_str = "{0:8.3f}".format(self.dm) if self.dm else 'None'
        return '{name:s} [P0 = {p.period:.9e}, W = {p.width:3d}, DM = {dm_str:s}, S/N = {p.snr:6.2f}]'.format(p=self, dm_str=dm_str, name=name)

    def __repr__(self):
        return str(self)



class Detection(Peak):
    """ A Detection represents a group of Peaks found at (nearly) the same
    period but at different width trials. Detections are the final product
    of the post-processing of a single DM trial. """
    def __init__(self, peaks, pgram, period_slice_width=1.0):
        """ """
        self.peaks = peaks
        top = max(peaks, key=operator.attrgetter('snr'))
        super(Detection, self).__init__(top.period, top.snr, top.dm, top.iw, top.width, top.ducy)

        # Extract a slice of the Periodogram that is 'period_slice_width'
        # DFT bins wide and centered on the peak
        dbis = pgram.tobs/pgram.periods
        period_slice_mask = abs(dbis - pgram.tobs/self.period) < (period_slice_width / 2.0)
        period_slice_indices = np.where(period_slice_mask)[0]
        self.period_trials = pgram.periods[period_slice_indices]
        self.snr_trials = pgram.snrs[period_slice_indices, :]
        self.width_trials = pgram.widths[:]
        self.metadata = pgram.metadata

    def plot(self):
        st = self.snr_trials
        wt = self.width_trials
        pt = self.period_trials

        # Delta period in microseconds
        dp = 1.0e6 * (pt - self.period)

        # Delta period step
        dp_step = np.diff(dp).mean()

        # X-axis limits
        xmin = dp[0]  - 0.5*dp_step
        xmax = dp[-1] + 0.5*dp_step

        gs = GridSpec(2, 2, width_ratios=(25, 1))

        plt.subplot(gs[0, 0])
        image = plt.imshow(
            st.T,
            extent=[dp[0]-0.5*dp_step, dp[-1]+0.5*dp_step, 0.0, wt.size],
            aspect='auto',
            origin='lower'
            )
        plt.yticks(np.arange(wt.size) + 0.5, wt)
        plt.ylabel('Boxcar Width (bins)', fontsize=12)
        plt.title(str(self))

        plt.subplot(gs[:, 1])
        cb = plt.colorbar(image, cax=plt.gca())
        cb.set_label(label='S/N', size=12)

        plt.subplot(gs[1, 0])
        plt.plot(dp, st[:, self.iw], label='S/N at W = {0:d}'.format(self.width))
        plt.xlabel('Delta Period (us)', fontsize=12)
        plt.xlim(xmin, xmax)
        plt.grid(linestyle=':')
        plt.legend(loc='upper left')
        plt.tight_layout()


    def display(self, figsize=(10, 6), dpi=100):
        plt.figure(figsize=figsize, dpi=dpi)
        self.plot()
        plt.show()



def find_peaks_single(pgram, iwidth, boundaries, min_segments=8, snr_min=6.5, nsigma=6.5, peak_clustering_radius=0.20, polydeg=2):
    periods = pgram.periods
    snrs = pgram.snrs[:, iwidth]
    width = pgram.widths[iwidth]
    tobs = pgram.tobs
    dm = pgram.metadata['dm']

    # Average number of bins used during the search
    bins_avg = pgram._plan.bins_avg

    stats = segment_stats(snrs, boundaries)

    # NOTE: tfunc is a function of period only. tfunc has one parameter expected
    # to be a numpy array
    if len(boundaries) < min_segments:
        #warnings.warn('find_peaks_single(): not enough segments for dynamic threshold fitting, applying constant S/N threshold')
        tfunc, polyco = threshold_function_static(snr_min=snr_min, polydeg=polydeg)
    else:
        tfunc, polyco = threshold_function_dynamic(stats, snr_min=snr_min, nsigma=nsigma, polydeg=polydeg)

    # This is our selection threshold as a function of *period*
    # (NOT log(period) this time)
    threshold = tfunc(periods)

    # Now find peaks: sets of period trials that lie above the threshold
    # Two points whose dft bin indexes lie within 'peak_clustering_radius'
    # of each other are considered part of the same peak
    peaks = []

    significant_mask = snrs > threshold
    significant_indices = np.where(significant_mask)[0]

    if len(significant_indices):
        # DFT bin indexes corresponding to the significant periodogram points
        dbi = tobs / periods[significant_mask]

        for cli in cluster_1d(dbi, peak_clustering_radius):
            peak_indices = significant_indices[cli]
            periods_slice = periods[peak_indices]
            snrs_slice = snrs[peak_indices]
            imax = snrs_slice.argmax()
            # NOTE: float() cast to avoid int division in Python2
            ducy = width / float(bins_avg)
            current_peak = Peak(periods_slice[imax], snrs_slice[imax], dm, iwidth, width, ducy)
            peaks.append(current_peak)

    return stats, polyco, threshold, peaks



def find_peaks(pgram, segment_dftbins_length=10.0, min_segments=8, snr_min=6.5, nsigma=6.5, peak_clustering_radius=0.20, polydeg=2, period_slice_width=1.0):
    ### Cut period trials into segments
    boundaries = segment(pgram.periods, pgram.tobs, segment_dftbins_length=segment_dftbins_length)

    all_peaks = []
    polyco_tracker = {}
    stats_tracker = {}

    for iwidth, width in enumerate(pgram.widths, start=0):
        stats, polyco, threshold, peaks = find_peaks_single(
            pgram,
            iwidth,
            boundaries,
            min_segments=min_segments,
            snr_min=snr_min,
            nsigma=nsigma,
            peak_clustering_radius=peak_clustering_radius,
            polydeg=polydeg
            )
        all_peaks = all_peaks + peaks
        polyco_tracker[width] = polyco
        stats_tracker[width] = stats

    # Second stage of clustering: group peaks with close periods but different
    # widths. Keep only the one with highest S/N
    detections = []
    dbi = np.asarray([pgram.tobs / peak.period for peak in all_peaks])
    for cluster_indices in cluster_1d(dbi, peak_clustering_radius):
        peak_group = [all_peaks[ix] for ix in cluster_indices]
        det = Detection(peak_group, pgram, period_slice_width=period_slice_width)
        detections.append(det)

    # TODO: find a way to return extra information about stats and the
    # threshold fit in a neat way. For now, just return the detections.
    return detections #, stats_tracker, polyco_tracker