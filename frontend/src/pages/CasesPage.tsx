import { Cases } from '../modules/cases';

export function CasesPage({ selectedCaseId, onSelectCase }: { selectedCaseId: string | null; onSelectCase: (caseId: string | null) => void }) {
  return <Cases selectedCaseId={selectedCaseId} onSelectCase={onSelectCase} />;
}
