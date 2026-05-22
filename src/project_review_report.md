# 📊 프로젝트 통합 코드 리뷰 리포트

## 📄 apps/web/app/(platform)/labs/page.tsx (124줄)

### 🔹 스타일 검사 결과
코드 스타일 위반 사항은 다음과 같습니다:

**[63라인] 위반 유형: 배열 인덱스를 key로 사용**
```
<LabCardSkeleton key={i} />
```
배열의 인덱스(`i`)를 React의 `key` prop으로 사용하는 것은 권장되지 않습니다. 리스트가 재정렬되거나 변경될 경우 렌더링 문제가 발생할 수 있습니다. 고유한 식별자를 사용하는 것이 바람직합니다.

---

**[22라인] 위반 유형: 내부 함수 선언 방식 불일치 (일관성 문제)**
```
function setFilter(value: Difficulty | 'all') { ... }
```
컴포넌트 내부의 다른 로직들은 `const` 화살표 함수 형태로 작성되는 것이 React/TypeScript 컨벤션에서 더 일반적입니다. 아래처럼 통일하는 것이 권장됩니다:
```ts
const setFilter = (value: Difficulty | 'all') => { ... };
```

---

**[94라인] 위반 유형: 컴포넌트 선언 순서 (호이스팅 의존)**
```
function LabCardSkeleton() { ... }
```
`LabCardSkeleton`이 `LabsCatalog` 내부에서 사용되지만, 파일의 맨 아래에 선언되어 있습니다. `function` 선언은 호이스팅되므로 동작은 하지만, 가독성과 유지보수를 위해 사용되기 전에 선언하거나 파일 상단에 배치하는 것이 일반적인 컨벤션입니다.

---

**[33라인] 위반 유형: queryKey 범위 미지정 (잠재적 캐시 충돌)**
```
queryKey: ['labs'],
```
`@tanstack/react-query` 사용 시 `queryKey`를 너무 단순하게 설정하면 다른 쿼리와 충돌할 수 있습니다. 일반적으로 `['labs', 'list']` 또는 `['labs', { filter }]`처럼 더 구체적인 키를 사용하는 것이 권장됩니다. 현재 `filter` 값이 변경되어도 데이터를 다시 fetch하지 않는 문제도 있습니다.

---

**[87라인] 위반 유형: `<Suspense>` fallback prop 누락**
```
<Suspense>
  <LabsCatalog />
</Suspense>
```
`<Suspense>` 컴포넌트에는 로딩 상태를 표시하기 위한 `fallback` prop을 명시하는 것이 React 컨벤션입니다. fallback 없이 사용하면 로딩 중 아무것도 렌더링되지 않습니다.
```tsx
<Suspense fallback={<div>Loading...</div>}>
```

### 🔹 보안 취약점 검사 결과
제공된 코드를 분석한 결과, 요청하신 세 가지 항목(SQL Injection, XSS, 하드코딩된 비밀번호)에 대해 다음과 같이 평가됩니다:

---

## 🔍 보안 취약점 분석 결과

### ✅ SQL Injection
- **해당 없음**: 이 코드는 순수 프론트엔드(React/Next.js) 클라이언트 컴포넌트입니다. DB 쿼리를 직접 실행하는 코드가 없으며, `api.labs.list()`를 통해 추상화된 API 호출만 수행합니다.

### ✅ 하드코딩된 비밀번호
- **해당 없음**: 코드 내에 비밀번호, API 키, 토큰 등 민감한 자격증명이 하드코딩된 부분은 발견되지 않습니다.

---

## ⚠️ 잠재적 보안 이슈

### 1. URL 파라미터 검증 미흡 (낮은 심각도)
- **위치**: `filter = (searchParams.get('difficulty') ?? 'all') as Difficulty | 'all'`
- **유형**: 입력값 미검증 (타입 단언 남용)
- **설명**: URL의 `difficulty` 파라미터를 타입 단언(`as`)으로만 처리하고, 실제 허용된 값인지 런타임 검증이 없습니다. 공격자가 임의의 값을 넣어도 코드가 그대로 처리합니다.
- **심각도**: 낮음 (현재 코드에서는 필터링 로직 오동작 수준이지만, 향후 해당 값이 서버로 전달될 경우 위험 증가)
- **수정 제안**:
```typescript
const VALID_DIFFICULTIES = ['all', 'beginner', 'intermediate', 'advanced'];
const raw = searchParams.get('difficulty') ?? 'all';
const filter = VALID_DIFFICULTIES.includes(raw) ? raw as Difficulty | 'all' : 'all';
```

### 2. XSS 직접 위험은 없으나 LabCard 컴포넌트 주의 필요 (중간 심각도 - 잠재적)
- **위치**: `<LabCard key={lab.id} lab={lab} />`
- **유형**: 잠재적 XSS (Stored/Reflected)
- **설명**: 이 컴포넌트 자체에서는 `dangerouslySetInnerHTML` 사용이 없어 직접적인 XSS는 없습니다. 그러나 서버 API(`api.labs.list()`)로부터 받은 데이터를 `LabCard` 내부에서 어떻게 렌더링하는지에 따라 XSS가 발생할 수 있습니다. `LabCard` 내부에서 `dangerouslySetInnerHTML`을 사용한다면 위험합니다.
- **수정 제안**: `LabCard` 컴포넌트 내 `dangerouslySetInnerHTML` 사용 여부 확인 및 사용 시 DOMPurify 등으로 새니타이징 적용.

### 3. 에러 메시지 정보 노출 (낮은 심각도)
- **위치**: `<p>Lab 목록을 불러오지 못했습니다. 백엔드 서버를 확인하세요.</p>`
- **유형**: 정보 노출 (Information Disclosure)
- **설명**: "백엔드 서버를 확인하세요"라는 메시지는 내부 아키텍처 구조를 암시하여 공격자에게 힌트를 제공할 수 있습니다.
- **수정 제안**: "잠시 후 다시 시도해 주세요." 등 중립적인 메시지로 변경.

---

## 📋 종합 요약

| 취약점 유형 | 발견 여부 | 심각도 |
|---|---|---|
| SQL Injection | ❌ 없음 | - |
| XSS (직접) | ❌ 없음 | - |
| XSS (잠재적, LabCard) | ⚠️ 확인 필요 | 중간 |
| 하드코딩된 비밀번호 | ❌ 없음 | - |
| URL 파라미터 미검증 | ⚠️ 있음 | 낮음 |
| 에러 메시지 정보 노출 | ⚠️ 있음 | 낮음 |

전반적으로 이 코드 자체는 심각한 보안 취약점은 없으나, `LabCard` 컴포넌트와 백엔드 API의 보안도 함께 검토하는 것을 권장합니다.

---

## 📄 apps/web/app/(platform)/layout.tsx (10줄)

### 🔹 스타일 검사 결과
제공된 코드를 Airbnb JavaScript/TypeScript 스타일 가이드 기준으로 검사한 결과, 주요 위반 사항은 발견되지 않았습니다.

다만 일반적인 스타일 관점에서 아래와 같은 사소한 점검 사항이 있습니다:

[3] 함수 표현식 권장: `export default function PlatformLayout(...)` 형태의 함수 선언식보다, named function expression(기명 함수 표현식) 사용이 Airbnb 가이드에서는 권장됩니다.
예시:
```ts
const PlatformLayout = function PlatformLayout({ children }: { children: React.ReactNode }) { ... };
export default PlatformLayout;
```

전반적으로 코드는 다음 규칙들을 잘 준수하고 있습니다:
- `var` 대신 적절한 변수 선언 방식 사용
- 일관된 들여쓰기 및 구조
- import 구문 정상 사용

### 🔹 보안 취약점 검사 결과
제공된 코드를 분석한 결과, 요청하신 세 가지 보안 취약점(SQL Injection, XSS, 하드코딩된 비밀번호)은 발견되지 않았습니다.

**이유:**
- 해당 코드는 단순한 React 레이아웃 컴포넌트로, 데이터베이스 쿼리나 사용자 입력 처리 로직이 전혀 없습니다.
- 외부 입력값을 렌더링하는 부분이 없으므로 XSS 위험도 없습니다.
- 비밀번호나 API 키 등 민감한 정보가 하드코딩된 부분도 없습니다.

**잠재적으로 검토할 사항 (현재 코드만으로는 판단 불가):**
- `<Navbar />` 컴포넌트 내부 구현에 따라 취약점이 존재할 수 있습니다.
- `children` prop으로 전달되는 컴포넌트에서 사용자 입력을 `dangerouslySetInnerHTML` 등으로 처리한다면 XSS 위험이 생길 수 있습니다.

**결론:** 현재 제공된 코드 자체에는 명확한 보안 취약점이 없습니다. 보다 정확한 보안 진단을 위해서는 `Navbar` 컴포넌트 코드, `children`에 해당하는 페이지 컴포넌트 코드, 그리고 백엔드/API 코드를 함께 검토하는 것이 필요합니다.

---

## 📄 apps/web/components/lab/LabCard.tsx (46줄)

### 🔹 스타일 검사 결과
제공된 TypeScript/React 코드에서 발견된 스타일 위반 사항은 다음과 같습니다.

[11번째 줄] 네이밍 컨벤션 위반 (변수명 축약):
`const diff = DIFFICULTY_CONFIG[lab.difficulty];`
→ `diff`는 지나치게 축약된 변수명입니다. `difficultyConfig` 또는 `difficultyStyle`처럼 의미를 명확히 전달하는 이름이 권장됩니다.

[19번째 줄] 네이밍 컨벤션 위반 (snake_case 프로퍼티명):
`{lab.duration_min}`
→ TypeScript/JavaScript에서는 객체 프로퍼티명에 camelCase를 사용하는 것이 일반적입니다. `durationMin`으로 변경하는 것이 권장됩니다. (단, 외부 API나 DB 스키마에서 유래한 타입이라면 예외일 수 있습니다.)

[34번째 줄] 네이밍 컨벤션 위반 (snake_case 프로퍼티명):
`{lab.step_count}`
→ 동일하게 `stepCount`로 변경하는 것이 TypeScript 컨벤션에 부합합니다.

전반적으로 코드 구조와 컴포넌트 설계는 양호하며, 주요 위반은 네이밍 컨벤션에 집중되어 있습니다.

### 🔹 보안 취약점 검사 결과
제공된 코드(`LabCard` React/Next.js 컴포넌트)를 분석한 결과는 다음과 같습니다.

---

## 🔍 보안 취약점 분석 결과

### 1. SQL Injection
- **결과: 해당 없음**
- 이 코드는 순수 프론트엔드 UI 컴포넌트로, 데이터베이스 쿼리를 직접 실행하지 않습니다.

---

### 2. XSS (Cross-Site Scripting)
- **결과: 잠재적 위험 존재 (심각도: 중간)**
- **위치:**
  - `{lab.title}`, `{lab.description}`, `{lab.tags}`, `{lab.duration_min}`, `{lab.step_count}` 등 외부 데이터를 렌더링하는 모든 부분
  - `href={/labs/${lab.id}}` — URL에 `lab.id`를 직접 삽입하는 부분

- **설명:**
  - React는 기본적으로 `{}` 내 문자열을 자동 이스케이프하므로, 일반적인 XSS는 방어됩니다.
  - 그러나 `dangerouslySetInnerHTML`을 향후 사용하거나, `lab.id`에 `javascript:` 같은 악성 값이 포함될 경우 `href`를 통한 XSS가 발생할 수 있습니다.

- **수정 제안:**
```typescript
// lab.id 검증 추가 (숫자 또는 안전한 슬러그만 허용)
const safeId = encodeURIComponent(lab.id);
href={`/labs/${safeId}`}

// 또는 서버/API 레이어에서 id를 UUID나 정수로 타입 제한
```

---

### 3. 하드코딩된 비밀번호
- **결과: 해당 없음**
- 코드 내 비밀번호, API 키, 토큰 등 민감 정보가 하드코딩된 부분은 없습니다.

---

### 4. 추가 주의사항

#### ⚠️ URL 파라미터 미검증 (심각도: 낮음)
- **위치:** `href={/labs/${lab.id}}`
- `lab.id`의 타입이 명확히 강제되지 않을 경우, 예상치 못한 경로 조작이 가능합니다.
- **수정 제안:** TypeScript 타입에서 `id: number` 또는 `id: string` (UUID 형식)으로 엄격히 제한하고, 런타임 검증을 추가하세요.

#### ⚠️ 데이터 출처 신뢰 문제 (심각도: 낮음)
- `lab` 객체가 외부 API나 사용자 입력에서 오는 경우, 컴포넌트에 전달되기 전에 서버 사이드에서 반드시 유효성 검사(validation)와 살균(sanitization)을 수행해야 합니다.

---

## ✅ 종합 평가

| 취약점 유형 | 발견 여부 | 심각도 |
|---|---|---|
| SQL Injection | ❌ 없음 | - |
| XSS | ⚠️ 잠재적 위험 | 중간 |
| 하드코딩된 비밀번호 | ❌ 없음 | - |
| URL 파라미터 미검증 | ⚠️ 주의 필요 | 낮음 |

전반적으로 이 컴포넌트는 React의 기본 보안 특성 덕분에 심각한 취약점은 없으나, `lab.id`의 입력값 검증과 데이터 출처에 대한 서버 사이드 검증을 강화하는 것이 권장됩니다.

---

## 📄 apps/web/components/ui/Navbar.tsx (54줄)

### 🔹 스타일 검사 결과
발견된 스타일 규칙 위반 사항은 다음과 같습니다:

[16] **함수 선언 방식**: `handleLogout`이 일반 함수 선언(`async function handleLogout()`)으로 작성되었습니다. Airbnb 스타일 가이드에서는 이름 있는 함수 표현식(named function expression) 사용을 권장하므로, `const handleLogout = async () => { ... }` 형태로 작성하는 것이 적합합니다.

[23] **클래스명 순서 / 가독성**: `max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between` — Tailwind CSS를 사용할 경우 일반적으로 클래스 순서 컨벤션(레이아웃 → 크기 → 간격 → 색상 등)을 따르는 것이 권장됩니다. `h-14`가 `flex` 앞에 위치하지 않고 중간에 삽입되어 있어 일관성이 부족합니다. (프로젝트 컨벤션에 따라 다를 수 있으나 일반적인 지적 사항입니다.)

[16~19] **에러 핸들링 방식**: `.catch(() => {})` 로 에러를 무시하고 있습니다. 빈 catch 블록은 오류를 묵살하여 디버깅을 어렵게 만들므로, 최소한 로깅 처리(`console.error` 등)를 추가하는 것이 권장됩니다.

[7~11] **객체 후행 쉼표(trailing comma)**: `NAV_LINKS` 배열의 마지막 요소 `{ href: '/instructor', label: '강사 모드' }` 뒤에 후행 쉼표가 없습니다. Airbnb 스타일 가이드는 객체와 배열에서 후행 쉼표 사용을 권장합니다.

예시 수정:
```ts
const NAV_LINKS = [
  { href: '/labs', label: 'Labs' },
  { href: '/leaderboard', label: '리더보드' },
  { href: '/instructor', label: '강사 모드' }, // ← 후행 쉼표 추가
];
```

```ts
// 함수 표현식으로 변경
const handleLogout = async () => {
  await api.auth.logout().catch((e) => { console.error(e); });
  window.location.href = '/login';
};
```

### 🔹 보안 취약점 검사 결과
제공된 코드(`Navbar` 컴포넌트)를 분석한 결과, 요청하신 세 가지 항목(SQL Injection, XSS, 하드코딩된 비밀번호)에 대한 결과는 다음과 같습니다.

---

## ✅ 검사 결과 요약

| 취약점 유형 | 발견 여부 |
|---|---|
| SQL Injection | ❌ 해당 없음 |
| XSS | ⚠️ 잠재적 위험 존재 |
| 하드코딩된 비밀번호 | ❌ 해당 없음 |

---

## ⚠️ 발견된 잠재적 취약점

### 1. XSS - `pathname.startsWith(link.href)` 를 통한 클래스 조작
- **위치**: `pathname.startsWith(link.href)` 조건부 className 렌더링 부분
- **유형**: Reflected XSS (간접적)
- **심각도**: 낮음 (Low) — Next.js가 pathname을 자동으로 인코딩하므로 직접적인 위험은 낮음
- **설명**: `usePathname()`으로 가져온 URL 경로값이 직접 DOM에 렌더링되진 않지만, 만약 pathname 값이 조작되어 className에 예기치 않은 문자열이 삽입될 경우 스타일 기반 공격 벡터가 될 수 있습니다.
- **수정 제안**: pathname 값을 사용할 때 화이트리스트 기반으로 허용된 경로인지 검증하는 로직을 추가하는 것이 좋습니다.

```typescript
const isActive = NAV_LINKS.some(l => l.href === link.href) && pathname.startsWith(link.href);
```

---

### 2. 로그아웃 후 리다이렉션 - Open Redirect 가능성
- **위치**: `window.location.href = '/login';`
- **유형**: Open Redirect (간접적)
- **심각도**: 낮음 (Low)
- **설명**: 현재는 하드코딩된 `/login`으로 이동하므로 안전하지만, 만약 이 값이 외부 파라미터(예: `?redirect=...`)로 변경된다면 악의적인 URL로 리다이렉트될 수 있습니다.
- **수정 제안**: `router.push('/login')`을 사용하는 것이 Next.js 환경에서 더 안전하고 권장되는 방식입니다.

```typescript
import { useRouter } from 'next/navigation';

const router = useRouter();

async function handleLogout() {
  await api.auth.logout().catch(() => {});
  router.push('/login'); // window.location.href 대신 사용
}
```

---

## ✅ 안전한 항목

- **SQL Injection**: 이 컴포넌트는 순수 UI 컴포넌트로 DB 쿼리를 직접 다루지 않아 해당 없음
- **하드코딩된 비밀번호/시크릿**: 발견되지 않음
- **`dangerouslySetInnerHTML` 사용**: 없음 → XSS 직접 위험 없음
- **링크(`href`)**: 모두 정적 상수로 정의되어 있어 안전함

---

## 📌 추가 권장 사항

- `강사 모드` 링크(`/instructor`)는 인가(Authorization) 없이 누구나 접근할 수 있으므로, 라우트 레벨에서 **접근 제어(OWASP A01 - Broken Access Control)** 를 반드시 적용해야 합니다.
- `api.auth.logout()`의 오류를 `.catch(() => {})`로 무시하고 있어, 로그아웃 실패 시 사용자에게 피드백이 없습니다. 보안 로깅 관점에서 에러를 적절히 처리하는 것을 권장합니다.

---

## 📄 apps/api/internal/api/handlers/lab.go (84줄)

### 🔹 스타일 검사 결과
Go 언어의 일반적인 컨벤션 기준으로 분석한 스타일 위반 사항입니다.

**[10] 주석 스타일 위반: 패키지 수준 변수 주석**
- `mockLabs`는 exported 변수가 아니므로 필수는 아니지만, 주석이 변수 선언 바로 위에 붙어 있는 건 적절합니다. 다만 주석이 두 줄로 분리되어 있는데, Go 컨벤션상 여러 줄 주석은 `/* */` 보다 `//` 연속 사용이 권장됩니다. 이 부분은 이미 지켜지고 있으나, 주석 내용이 코드 관리 메모(TODO성)이므로 `// TODO:` 형식으로 명시하는 것이 관례입니다.

**[63] 주석 스타일 위반: exported 함수 주석 형식**
- `ListLabs`는 exported 함수이므로 Go 컨벤션상 주석은 반드시 `// ListLabs ...` 형태로 함수명으로 시작해야 합니다. 현재 `// ListLabs는 ...`로 한국어 조사가 바로 붙어 있어 영문 기준 godoc 컨벤션(`// ListLabs returns ...`)을 따르지 않습니다.

**[71] 주석 스타일 위반: exported 함수 주석 형식**
- `GetLab`도 동일하게 `// GetLab은 ...` 형태로 영문 godoc 컨벤션(`// GetLab returns ...`)을 따르지 않습니다.

**[65~68] 스타일 권장사항: 응답 구조체 미사용**
- `gin.H`(즉, `map[string]interface{}`)를 직접 응답으로 사용하고 있습니다. Go 컨벤션에서는 명확한 타입 정의(`struct`)를 사용하는 것이 권장됩니다. 타입 안전성이 없고 오탈자 발생 가능성이 있습니다.

**[11~57] 스타일 권장사항: 하드코딩 데이터에 타입 없음**
- `mockLabs`의 타입이 `[]gin.H`(즉, `[]map[string]interface{}`)로 선언되어 있어 각 필드에 대한 타입 안전성이 없습니다. Go 컨벤션상 구조체 슬라이스(`[]Lab`)로 정의하는 것이 바람직합니다.

요약:

| 라인 | 위반 유형 | 설명 |
|------|----------|------|
| 10~11 | 주석 형식 | TODO성 주석은 `// TODO:` 형식으로 명시 권장 |
| 63 | godoc 주석 형식 | exported 함수 주석은 영문으로 함수명 시작 권장 (`// ListLabs returns ...`) |
| 71 | godoc 주석 형식 | 동일하게 `// GetLab returns ...` 형태 권장 |
| 11, 64 | 타입 안전성 | `gin.H` 대신 명시적 struct 타입 사용 권장 |

### 🔹 보안 취약점 검사 결과
제공된 Go 코드(handlers 패키지)를 SQL Injection, XSS, 하드코딩된 비밀번호 관점에서 분석한 결과는 다음과 같습니다.

---

## 분석 결과 요약

요청하신 세 가지 취약점 유형에 대해:

### ✅ SQL Injection
- **해당 없음**: 코드 내에 데이터베이스 쿼리가 전혀 존재하지 않으며, 하드코딩된 `mockLabs` 슬라이스를 사용하므로 SQL Injection 취약점 없음.

### ✅ XSS (Cross-Site Scripting)
- **직접적 취약점 없음**: Gin의 `c.JSON()`은 응답을 JSON으로 직렬화하며, Content-Type을 `application/json`으로 설정합니다. 이 경우 브라우저가 HTML로 해석하지 않으므로 XSS 위험은 낮음.
- 단, `GetLab`에서 `:id` path parameter를 그대로 응답에 포함하지는 않고 조회 키로만 사용하므로 현재 코드에서 XSS 위험은 없음.

### ✅ 하드코딩된 비밀번호
- **해당 없음**: 코드 내에 비밀번호, API 키, 토큰 등 민감한 자격 증명이 하드코딩된 부분 없음.

---

## ⚠️ 실제로 존재하는 보안 취약점 및 개선 사항

### 1. 인증/인가 미검증 (심각도: 높음)
- **위치**: `ListLabs`, `GetLab` 함수
- **유형**: A01:2021 – Broken Access Control / A07:2021 – Identification and Authentication Failures
- **설명**: 코드 주석에 "인증 필요"라고 명시되어 있으나, 함수 내부에 실제 인증 토큰 검증 로직이 없음. 미들웨어에서 처리한다고 가정해도 코드 자체에서 확인 불가.
- **수정 제안**: Gin 미들웨어 체인에 JWT 또는 세션 기반 인증 미들웨어를 명시적으로 적용하고, 라우터 등록 시 인증 그룹으로 묶어야 함.
```go
authorized := router.Group("/api/v1")
authorized.Use(AuthMiddleware())
{
    authorized.GET("/labs", handler.ListLabs)
    authorized.GET("/labs/:id", handler.GetLab)
}
```

### 2. 하드코딩된 Mock 데이터 사용 (심각도: 낮음 / 운영 리스크)
- **위치**: `mockLabs` 전역 변수
- **유형**: A05:2021 – Security Misconfiguration
- **설명**: 주석에 "임시 데이터"라고 명시되어 있으나, 운영 환경에 그대로 배포될 경우 실제 데이터와 혼재될 위험이 있음.
- **수정 제안**: 빌드 태그(`//go:build dev`) 또는 환경 변수를 통해 mock 데이터 사용 여부를 분리.

### 3. 에러 정보 노출 (심각도: 낮음)
- **위치**: `GetLab` 함수의 `h.err(c, http.StatusNotFound, "lab not found")`
- **유형**: A05:2021 – Security Misconfiguration
- **설명**: 현재는 단순 문자열이지만, 에러 핸들러(`h.err`) 구현에 따라 내부 스택 트레이스나 시스템 정보가 노출될 가능성이 있음.
- **수정 제안**: 에러 응답에는 사용자에게 필요한 최소한의 정보만 포함하고, 상세 로그는 서버 내부에서만 기록.

---

## 결론

| 취약점 유형 | 존재 여부 | 심각도 |
|---|---|---|
| SQL Injection | ❌ 없음 | - |
| XSS | ❌ 없음 | - |
| 하드코딩된 비밀번호 | ❌ 없음 | - |
| 인증/인가 미검증 | ⚠️ 불확실 | 높음 |
| Mock 데이터 운영 혼재 | ⚠️ 잠재적 | 낮음 |
| 에러 정보 노출 | ⚠️ 잠재적 | 낮음 |

요청하신 세 가지 주요 취약점은 현재 코드에서 발견되지 않았으나, 인증/인가 처리 부분은 미들웨어 코드까지 함께 검토하는 것을 권장합니다.

---

