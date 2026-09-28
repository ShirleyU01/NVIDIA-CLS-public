import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import { isTeacherAuthed, setTeacherAuthed } from './auth/teacherAuth'
import { GuidedTour } from './components/GuidedTour'
import { RequireTeacherAuth } from './components/RequireTeacherAuth'
import { useStudentTour } from './hooks/useStudentTour'
import { HomePage } from './pages/HomePage'
import { LandingPage } from './pages/LandingPage'
import { StudentAssessmentsPage } from './pages/StudentAssessmentsPage'
import { StudentDonePage } from './pages/StudentDonePage'
import { StudentHomePage } from './pages/StudentHomePage'
import { StudentPrepPage } from './pages/StudentPrepPage'
import { StudentStudyConfigPage } from './pages/StudentStudyConfigPage'
import { StudentStudyIdPage } from './pages/StudentStudyIdPage'
import { StudentSessionPage } from './pages/StudentSessionPage'
import { StudentStudyPrepPage } from './pages/StudentStudyPrepPage'
import { StudentExitSurveyPage } from './pages/StudentExitSurveyPage'
import { StudentStudyReviewPage } from './pages/StudentStudyReviewPage'
import { StudentStudySessionPage } from './pages/StudentStudySessionPage'
import { StudentStudyPostSessionPage } from './pages/StudentStudyPostSessionPage'
import { TeacherAssessmentsPage } from './pages/TeacherAssessmentsPage'
import { TeacherAssessmentDetailPage } from './pages/TeacherAssessmentDetailPage'
import { TeacherCreateExamPage } from './pages/TeacherCreateExamPage'
import { TeacherDonePage } from './pages/TeacherDonePage'
import { TeacherFeedbackSubmittedPage } from './pages/TeacherFeedbackSubmittedPage'
import { TeacherFeedbackPage } from './pages/TeacherFeedbackPage'
import { TeacherReviewPage } from './pages/TeacherReviewPage'
import { TeacherSessionDetailPage } from './pages/TeacherSessionDetailPage'
import { TeacherStudyDashboardPage } from './pages/TeacherStudyDashboardPage'
import { TeacherLoginPage } from './pages/TeacherLoginPage'
import { NotFoundPage } from './pages/placeholders'
import { ROUTE_PATH } from './routes/paths'
import './App.css'

function App() {
  const studentTour = useStudentTour()
  const location = useLocation()
  const navigate = useNavigate()

  const showTeacherLogout =
    location.pathname.startsWith('/teacher') &&
    location.pathname !== ROUTE_PATH.TEACHER_LOGIN &&
    isTeacherAuthed()

  const handleTeacherLogout = () => {
    setTeacherAuthed(false)
    navigate(ROUTE_PATH.HOME, { replace: true })
  }

  return (
    <div className="app-shell" data-testid="app-shell" aria-label="Socrates web app">
      <header className="app-shell__header">
        <p className="app-shell__kicker">Socrates</p>
        {showTeacherLogout ? (
          <button type="button" className="app-shell__guide-button" onClick={handleTeacherLogout}>
            Logout
          </button>
        ) : null}
        {studentTour.showStudentGuide ? (
          <button type="button" className="app-shell__guide-button" onClick={studentTour.start}>
            Student Guide
          </button>
        ) : null}
      </header>
      <Routes>
        <Route path={ROUTE_PATH.HOME} element={<LandingPage />} />
        <Route path={ROUTE_PATH.TEACHER_LEGACY_HOME} element={<Navigate to={ROUTE_PATH.TEACHER_HOME} replace />} />
        <Route path={ROUTE_PATH.TEACHER_LOGIN} element={<TeacherLoginPage />} />
        <Route element={<RequireTeacherAuth />}>
          <Route path={ROUTE_PATH.TEACHER_HOME} element={<HomePage />} />
          <Route path={ROUTE_PATH.TEACHER_ASSESSMENTS} element={<TeacherAssessmentsPage />} />
          <Route path={ROUTE_PATH.TEACHER_STUDY_DASHBOARD} element={<TeacherStudyDashboardPage />} />
          <Route
            path={ROUTE_PATH.TEACHER_ASSESSMENT_DETAIL}
            element={<TeacherAssessmentDetailPage />}
          />
          <Route path={ROUTE_PATH.TEACHER_SESSION_DETAIL} element={<TeacherSessionDetailPage />} />
          <Route path={ROUTE_PATH.TEACHER_CREATE_EXAM} element={<TeacherCreateExamPage />} />
          <Route path={ROUTE_PATH.TEACHER_REVIEW} element={<TeacherReviewPage />} />
          <Route path={ROUTE_PATH.TEACHER_FEEDBACK} element={<TeacherFeedbackPage />} />
          <Route
            path={ROUTE_PATH.TEACHER_FEEDBACK_SUBMITTED}
            element={<TeacherFeedbackSubmittedPage />}
          />
          <Route path={ROUTE_PATH.TEACHER_DONE} element={<TeacherDonePage />} />
        </Route>
        <Route path={ROUTE_PATH.STUDENT_HOME} element={<StudentHomePage />} />
        <Route path={ROUTE_PATH.STUDENT_ASSESSMENTS} element={<StudentAssessmentsPage />} />
        <Route path={ROUTE_PATH.STUDENT_PREP} element={<StudentPrepPage />} />
        <Route path={ROUTE_PATH.STUDENT_SESSION} element={<StudentSessionPage />} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_PREP} element={<StudentStudyPrepPage />} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_ID} element={<StudentStudyIdPage />} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_CONFIG} element={<StudentStudyConfigPage />} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_SESSION} element={<StudentStudySessionPage />} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_REVIEW} element={<StudentStudyReviewPage />} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_POST_SESSION} element={<StudentStudyPostSessionPage />} />
        <Route path={ROUTE_PATH.STUDENT_STUDY_SURVEY} element={<StudentExitSurveyPage />} />
        <Route path={ROUTE_PATH.STUDENT_DONE} element={<StudentDonePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <GuidedTour
        isOpen={studentTour.isOpen}
        steps={studentTour.steps}
        onFinish={studentTour.finish}
        onSkip={studentTour.skip}
      />
    </div>
  )
}

export default App
