/** empathy_generator 输出 → EmpathyView（脏数据兜底） */
import type { EmpathyView, Json } from './types';

export function buildEmpathyView(raw: Json | null): EmpathyView {
  const response = typeof raw?.empathetic_response === 'string' ? raw.empathetic_response.trim() : '';
  const persona = typeof raw?.teacher_persona === 'string' ? raw.teacher_persona.trim() : '';
  const techniques = Array.isArray(raw?.psychological_techniques)
    ? raw.psychological_techniques.filter((t): t is string => typeof t === 'string' && t.trim() !== '')
    : [];
  return { response, persona, techniques, hasData: response !== '' || persona !== '' || techniques.length > 0 };
}
