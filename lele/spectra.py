"""Relative spectra from printed lines; no experiment fitting or new calculation."""
import numpy as np
from ase.units import _hplanck, _c, _k

HC_EV_NM=1239.841984332


def broaden(x, centers, strengths, fwhm, shape='Gaussian'):
    if not np.isfinite(fwhm) or fwhm<=0:raise ValueError('FWHM must be positive')
    x=np.asarray(x);result=np.zeros_like(x,dtype=float)
    for center,strength in zip(centers,strengths):
        d=x-center
        if shape=='Lorentzian':
            g=fwhm/2;result+=strength*g/(np.pi*(d*d+g*g))
        else:
            s=fwhm/np.sqrt(8*np.log(2));result+=strength*np.exp(-.5*(d/s)**2)/(s*np.sqrt(2*np.pi))
    return result


def raman_strength(frequency,activity,laser_nm=532.,temperature=298.15):
    if frequency<=0 or activity is None:return None
    laser=1e7/laser_nm
    if frequency>=laser:return None
    thermal=-np.expm1(-_hplanck*_c*100*frequency/(_k*temperature))
    return activity*(laser-frequency)**4/(frequency*thermal)


def vibrational_lines(analysis,kind='IR',scale=1.,laser_nm=532.,temperature=298.15):
    lines=[]
    for mode in analysis.modes:
        frequency=mode.frequency_cm1*scale
        if frequency<=0:continue
        raw=mode.ir_intensity if kind=='IR' else mode.raman_activity
        value=raw if kind=='IR' else raman_strength(frequency,raw,laser_nm,temperature)
        if value is not None:lines.append((frequency,float(value),mode,raw))
    return lines


def simulated_spectrum(document,kind='IR',calculation=0,*,fwhm=15.,shape='Gaussian',scale=1.,
                       laser_nm=532.,temperature=298.15,wavelength=True,points=5000):
    if kind=='UV-Vis':
        transitions=[t for t in document.electronic_spectra[calculation].transitions if t.oscillator_strength is not None]
        centers=[t.energy_ev for t in transitions];strengths=[t.oscillator_strength for t in transitions]
        if not centers:raise ValueError('No TD transitions in this calculation')
        low=max(.05,min(centers)-max(1.,5*fwhm));high=max(centers)+max(1.,5*fwhm)
        x=np.linspace(HC_EV_NM/high,HC_EV_NM/low,points) if wavelength else np.linspace(low,high,points)
        energy=HC_EV_NM/x if wavelength else x
        y=broaden(energy,centers,strengths,fwhm,shape)
        label='Wavelength (nm)' if wavelength else 'Energy (eV)'
    else:
        lines=vibrational_lines(document.vibrations[calculation],kind,scale,laser_nm,temperature)
        if not lines:raise ValueError(f'No positive frequencies with printed {kind} data')
        centers=[r[0] for r in lines];strengths=[r[1] for r in lines]
        x=np.linspace(0,max(4000.,max(centers)+8*fwhm),points)
        y=broaden(x,centers,strengths,fwhm,shape);label='Wavenumber (cm⁻¹)'
    if y.max()>0:y/=y.max()
    return x,y,label
