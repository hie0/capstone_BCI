# 캡스톤 디자인 주제 구체화

## 1. 주제

**2-Class (Left-Hand / Right-Hand) Motor Imagery EEG를 활용한 실시간 미니게임 웹·앱 개발**

---

## 2. 프로젝트 개요

사용자의 **좌·우 손 Motor Imagery(운동 상상) EEG 신호**를 분류하여 웹/앱 내 미니게임을 조작하는 **BCI(Brain-Computer Interface) 시스템**을 개발한다.

EEG 장비를 통해 **Left-hand / Right-hand Motor Imagery 데이터**를 수집하고, 신호 전처리 및 특징 추출을 진행한다. 이후 머신러닝 기반 분류 모델을 적용하여 실시간으로 사용자의 좌·우 운동 상상 의도를 판별한다.

최종적으로 분류 결과를 게임의 입력값으로 활용하여, 사용자가 실제로 손을 움직이지 않고 **EEG 신호만으로 게임을 플레이할 수 있는 시스템**을 구현하는 것을 목표로 한다.

---

## 3. 주요 기술

### EEG 데이터 처리

* Left-hand / Right-hand Motor Imagery EEG 데이터 수집
* EEG 신호 전처리
* Mu/Beta 대역 분석
* Artifact 제거 및 신호 정규화

### 특징 추출

* CSP (Common Spatial Pattern)
* PSD (Power Spectral Density)
* Mu/Beta 대역 기반 특징 추출

### EEG 분류

* LDA (Linear Discriminant Analysis)
* SVM (Support Vector Machine)
* 기타 머신러닝 기반 분류 모델 비교

### 실시간 시스템

* 실시간 EEG 데이터 입력
* EEG 신호 전처리
* 특징 추출
* Left / Right 분류
* 분류 결과를 게임 입력으로 전달

---

## 4. 예상 콘텐츠

### 1) 좌·우 이동 기반 장애물 피하기 게임

* Left-hand MI → 왼쪽 이동
* Right-hand MI → 오른쪽 이동
* 좌·우 움직임을 활용하여 장애물을 피하는 게임

### 2) 리듬 타이밍 게임

* 화면에 나타나는 방향 또는 타이밍에 맞춰 Motor Imagery 수행
* EEG 분류 결과와 정답을 비교하여 점수 계산

### 3) O/X 선택 퀴즈

* Left / Right EEG 분류 결과를 O/X 선택에 활용
* 문제에 대한 답을 손 움직임 없이 선택

### 4) 제로게임

* 좌·우 선택 기반 심리게임
* EEG를 이용해 선택지를 결정
* 추후 멀티플레이 기능 구현 가능성 검토

---

## 5. 진행 방향

1. **Motor Imagery EEG 데이터 수집 및 전처리**

   * Left-hand / Right-hand EEG 데이터 수집
   * 노이즈 제거 및 필요한 주파수 대역 추출

2. **Mu/Beta 대역 기반 특징 추출 및 좌·우 클래스 분류**

   * EEG 특징 추출
   * 머신러닝 모델 학습 및 성능 비교

3. **실시간 EEG 입력 파이프라인 구축**

   * 실시간 EEG 데이터 수신
   * 전처리 → 특징 추출 → 분류 과정 구축

4. **웹/앱 게임과 EEG 분류 결과 연동**

   * Left / Right 분류 결과를 게임 입력으로 변환
   * 미니게임 조작 기능 구현

5. **정확도 및 사용자 경험 평가**

   * EEG 분류 정확도 평가
   * 실시간 반응 속도 평가
   * 게임 조작 성공률 및 사용자 경험 평가

---

## 6. 최종 목표

**Left-Hand / Right-Hand Motor Imagery EEG 신호를 실시간으로 분류하고, 해당 결과를 웹·앱 미니게임의 입력으로 활용하여 사용자가 신체 움직임 없이 뇌파만으로 게임을 조작할 수 있는 BCI 기반 인터랙티브 시스템을 구현한다.**
