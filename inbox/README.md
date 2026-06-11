# inbox — 주간 리포트(PDF) 추출본 투입 폴더

사이트 헤더의 **📄 리포트** 버튼으로 주간 참고 PDF를 올리면 브라우저가 본문을 추출해
`agro-report-<해당주월요일>.json` 파일을 내려받습니다. 그 파일을 **이 폴더에 넣어** 두면,
다음 주간 생성(`farmhannong-weekly-cards`)에서 해당 주차의 카드 20건(`origin:"pdf"`)으로
변환되어 자체검색 20건과 합쳐 총 40건으로 사이트에 반영됩니다.

- 파일 형식: `{ generatedFor, sourceName, pageCount, charCount, fullText, segments[] }`
- 같은 주차 파일이 여러 개면 가장 최근(파일명/수정시각) 것을 사용합니다.
- 처리(번역·요약)는 정적 사이트가 아니라 주간 생성 단계(관리자/Claude)에서 이뤄집니다.
- 처리 완료된 파일은 `inbox/processed/`로 옮겨 보관합니다.
