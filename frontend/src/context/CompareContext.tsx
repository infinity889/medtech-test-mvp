import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

export interface ComparedClinicRef {
  id: string;
  clinic_name: string;
  city: string;
}

const STORAGE_KEY = 'medprice_compare_clinics_v1';
export const MAX_COMPARE_CLINICS = 5;

interface CompareContextValue {
  clinics: ComparedClinicRef[];
  maxClinics: number;
  isSelected: (clinicId: string) => boolean;
  addClinic: (clinic: ComparedClinicRef) => boolean;
  removeClinic: (clinicId: string) => void;
  toggleClinic: (clinic: ComparedClinicRef) => void;
  clearAll: () => void;
}

const CompareContext = createContext<CompareContextValue | null>(null);

function loadStoredClinics(): ComparedClinicRef[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (item): item is ComparedClinicRef =>
          typeof item === 'object' &&
          item !== null &&
          typeof (item as ComparedClinicRef).id === 'string' &&
          typeof (item as ComparedClinicRef).clinic_name === 'string' &&
          typeof (item as ComparedClinicRef).city === 'string',
      )
      .slice(0, MAX_COMPARE_CLINICS);
  } catch {
    return [];
  }
}

export function CompareProvider({ children }: { children: ReactNode }) {
  const [clinics, setClinics] = useState<ComparedClinicRef[]>(() => loadStoredClinics());

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(clinics));
    } catch {
      // Ignore storage quota errors in restricted browsers
    }
  }, [clinics]);

  const isSelected = useCallback(
    (clinicId: string) => clinics.some((c) => c.id === clinicId),
    [clinics],
  );

  const addClinic = useCallback((clinic: ComparedClinicRef): boolean => {
    let added = false;
    setClinics((prev) => {
      if (prev.some((c) => c.id === clinic.id) || prev.length >= MAX_COMPARE_CLINICS) {
        return prev;
      }
      added = true;
      return [...prev, clinic];
    });
    return added;
  }, []);

  const removeClinic = useCallback((clinicId: string) => {
    setClinics((prev) => prev.filter((c) => c.id !== clinicId));
  }, []);

  const toggleClinic = useCallback((clinic: ComparedClinicRef) => {
    setClinics((prev) => {
      if (prev.some((c) => c.id === clinic.id)) {
        return prev.filter((c) => c.id !== clinic.id);
      }
      if (prev.length >= MAX_COMPARE_CLINICS) {
        return prev;
      }
      return [...prev, clinic];
    });
  }, []);

  const clearAll = useCallback(() => {
    setClinics([]);
  }, []);

  const value = useMemo<CompareContextValue>(
    () => ({
      clinics,
      maxClinics: MAX_COMPARE_CLINICS,
      isSelected,
      addClinic,
      removeClinic,
      toggleClinic,
      clearAll,
    }),
    [clinics, isSelected, addClinic, removeClinic, toggleClinic, clearAll],
  );

  return <CompareContext.Provider value={value}>{children}</CompareContext.Provider>;
}

export function useCompare(): CompareContextValue {
  const ctx = useContext(CompareContext);
  if (!ctx) {
    throw new Error('useCompare must be used inside CompareProvider');
  }
  return ctx;
}
