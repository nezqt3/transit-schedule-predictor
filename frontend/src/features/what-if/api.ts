import { apiPost } from '@/lib/api/http'
import type { WhatIfRequest, WhatIfResponse } from '@/types/api'

export function analyzeWhatIf(payload: WhatIfRequest) {
  return apiPost<WhatIfResponse, WhatIfRequest>('/what-if/analyze', payload)
}
