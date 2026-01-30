import { useRef, useState, useEffect } from 'react';
import {
  ActionIcon,
  Button,
  Icon,
  Tag,
  Text,
  TextArea,
  ThemeProvider,
} from '@lobehub/ui';
import {
  ArrowUpRight,
  Briefcase,
  ClipboardCheck,
  Download,
  Edit3,
  FileText,
  FolderOpen,
  FolderPlus,
  Landmark,
  Languages,
  ListChecks,
  Paperclip,
  Plus,
  Trash,
  Upload,
  X,
} from 'lucide-react';
import q2Financials from './docs/q2-financials.txt?raw';
import termSheet from './docs/term-sheet.txt?raw';
import kycAml from './docs/kyc-aml.txt?raw';
import appraisal from './docs/appraisal.txt?raw';
import industryOutlook from './docs/industry-outlook.txt?raw';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const createId = () => Math.random().toString(36).slice(2, 10);

// 智能 API 地址检测：
// - 开发环境：使用空字符串通過 Vite proxy 轉發到後端
// - 生产环境：使用空字符串（相对路径，与前端同域名）
const apiBase = import.meta.env.DEV 
  ? ''
  : '';

const nowTime = () =>
  new Date().toLocaleTimeString('zh-TW', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
  });

// Estimate pages based on content length (roughly 3000 chars per page)
const estimatePages = (content) => {
  if (!content) return '-';
  const chars = content.length;
  return Math.max(1, Math.ceil(chars / 3000));
};

const initialDocs = [];


// 預定義的任務階段
const predefinedStages = [
  { id: 'analyze', label: '需求分析', order: 1 },
  { id: 'search', label: '搜尋資料', order: 2 },
  { id: 'process', label: '處理內容', order: 3 },
  { id: 'complete', label: '任務完成', order: 4 },
];

const initialRoutingSteps = [];

const initialMessages = [];

// Generate case ID based on date
const generateCaseId = () => {
  const now = new Date();
  const prefix = 'CASE';
  const dateStr = now.toISOString().slice(2, 10).replace(/-/g, '');
  const random = Math.random().toString(36).slice(2, 5).toUpperCase();
  return `${prefix}-${dateStr}-${random}`;
};

// Calculate SLA remaining time
const calculateSlaRemaining = (startTime, slaDurationMinutes = 45) => {
  if (!startTime) return `${slaDurationMinutes} 分鐘`;
  const elapsed = Math.floor((Date.now() - startTime) / 60000);
  const remaining = slaDurationMinutes - elapsed;
  if (remaining <= 0) return '已逾時';
  return `剩餘 ${remaining} 分鐘`;
};

const summaryOutput = '';

const translationOutput = '';

const memoOutput = '';

const initialSummaryMetrics = [];

const initialRiskFlags = [];

const initialTranslationPairs = [];

const initialMemoSections = [];

const emptySummary = {
  output: summaryOutput,
  borrower: {
    name: '',
    description: '',
    rating: '',
  },
  metrics: initialSummaryMetrics,
  risks: initialRiskFlags,
};

const emptyTranslation = {
  output: translationOutput,
  clauses: initialTranslationPairs,
};

// 預設標籤分類
const workflowTags = ['待處理', '處理中', '已完成', '需補件', '已歸檔'];
const functionTags = ['摘要', '翻譯', '納入報告', '風險掃描', '背景資料'];

const tagColors = {
  // 流程標籤
  待處理: 'orange',
  處理中: 'blue',
  已完成: 'green',
  需補件: 'red',
  已歸檔: 'default',
  // 功能標籤
  摘要: 'gold',
  翻譯: 'cyan',
  納入報告: 'green',
  風險掃描: 'volcano',
  背景資料: 'geekblue',
  背景: 'geekblue',
};

const statusMeta = {
  running: { label: '進行中', className: 'is-running' },
  queued: { label: '等待中', className: 'is-queued' },
  done: { label: '完成', className: 'is-done' },
};

const normalizeRiskLevel = (level = '') => {
  const raw = level.toString();
  const lowered = raw.toLowerCase();

  if (lowered.includes('high') || raw.includes('高')) {
    return { key: 'high', label: '高' };
  }
  if (lowered.includes('medium') || raw.includes('中')) {
    return { key: 'medium', label: '中' };
  }
  return { key: 'low', label: '低' };
};

export default function App() {
  // 登入狀態
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginError, setLoginError] = useState('');

  const [documents, setDocuments] = useState(initialDocs);
  const [selectedDocId, setSelectedDocId] = useState(initialDocs[0]?.id || '');
  const [currentDocForExport, setCurrentDocForExport] = useState(null); // 要匯出的文件
  const [showExportModal, setShowExportModal] = useState(false); // 匯出對話框
  const [recipientEmail, setRecipientEmail] = useState(''); // 收件人郵箱
  const [isExporting, setIsExporting] = useState(false); // 匯出中
  const [selectedNewsIds, setSelectedNewsIds] = useState([]); // 多選新聞 ID
  const [showBatchExportModal, setShowBatchExportModal] = useState(false); // 批次匯出對話框
  const [batchRecipientEmail, setBatchRecipientEmail] = useState(''); // 批次匯出收件人
  const [isBatchExporting, setIsBatchExporting] = useState(false); // 批次匯出中
  const [editingDocId, setEditingDocId] = useState(''); // For tag editing
  const [customTags, setCustomTags] = useState([]); // User-created tags
  const [newTagInput, setNewTagInput] = useState('');
  const [routingSteps, setRoutingSteps] = useState(initialRoutingSteps);
  const [currentStage, setCurrentStage] = useState(''); // 當前執行的階段 ID
  const [completedStages, setCompletedStages] = useState([]); // 已完成的階段 ID 列表
  const [messages, setMessages] = useState(initialMessages);
  const [composerText, setComposerText] = useState('');
  const [activeTab, setActiveTab] = useState('documents');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [streamingContent, setStreamingContent] = useState('');
  const [reasoningSummary, setReasoningSummary] = useState('');
  
  // 日誌區域自動滾動
  const logContainerRef = useRef(null);

  // Dynamic metadata states
  const [caseId] = useState(() => generateCaseId());
  const [caseStartTime] = useState(() => Date.now());
  const [slaMinutes] = useState(45);
  const [ownerName, setOwnerName] = useState('RM Desk');

  const [artifacts, setArtifacts] = useState({
    summaries: [],
    translations: [],  // Changed to array for history
    memo: {
      output: memoOutput,
      sections: initialMemoSections,
      recommendation: '',
      conditions: '',
    },
  });

  const [activeTranslationIndex, setActiveTranslationIndex] = useState(0);

  // 登入處理
  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginError('');
    
    try {
      console.log('🔐 [登入] 開始登入流程...');
      const loginUrl = `${apiBase || ''}/api/auth/login`;
      console.log('🔐 [登入] 請求 URL:', loginUrl);
      
      const response = await fetch(loginUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: loginUsername,
          password: loginPassword
        })
      });
      
      console.log('🔐 [登入] 收到回應，狀態:', response.status);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('🔐 [登入] 回應數據:', { success: data.success, hasToken: !!data.token });
      
      if (data.success && data.token) {
        // 將token存儲到localStorage
        localStorage.setItem('authToken', data.token);
        
        // 清空前端所有狀態（確保登入後是乾淨的）
        console.log('🗑️ [登入] 清空前端狀態...');
        setDocuments([]);
        setMessages([]);
        setArtifacts({
          summaries: [],
          translations: [],
          memo: { output: '', sections: [], recommendation: '', conditions: '' },
        });
        setRoutingSteps([]);
        setSelectedDocId('');
        console.log('✅ [登入] 前端狀態已清空');
        
        setIsAuthenticated(true);
        console.log('🔐 [登入] 登入成功');
      } else {
        setLoginError(data.error || '登入失敗');
        setLoginPassword('');
        console.log('🔐 [登入] 登入失敗:', data.error);
      }
    } catch (error) {
      console.error('🔐 [登入錯誤]', error);
      const errorMsg = error instanceof Error 
        ? `連線失敗: ${error.message}` 
        : '連線失敗，請稍後再試';
      setLoginError(errorMsg);
      setLoginPassword('');
    }
  };

  // 自動驗證已存在的token（已停用 - 改為每次都需重新登入以確保資料乾淨）
  useEffect(() => {
    // 每次頁面載入時清除舊 token，強制重新登入
    // 這樣可以確保每次開啟頁面都是乾淨的狀態
    const token = localStorage.getItem('authToken');
    if (token) {
      console.log('🔄 [初始化] 清除舊 token，需要重新登入');
      localStorage.removeItem('authToken');
      setIsAuthenticated(false);
    }
  }, []);

  // 日誌自動滾動到底部
  useEffect(() => {
    if (logContainerRef.current && reasoningSummary) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [reasoningSummary]);

  // 從數據庫載入新聞記錄（僅在登入後執行一次）
  useEffect(() => {
    if (!isAuthenticated) return;
    
    const loadNewsRecords = async () => {
      try {
        // 每次頁面載入時先清空所有資料（確保乾淨狀態）
        console.log('🗑️ [清空] 清空舊資料...');
        await fetch(`${apiBase || ''}/api/auth/clear-data`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        console.log('✅ [清空] 資料已清空');
        
        const response = await fetch(`${apiBase || ''}/api/news/records`);
        if (response.ok) {
          const data = await response.json();
          console.log('📰 [載入] 從資料庫載入記錄:', data.documents?.length, '筆');
          console.log('📰 [載入] 第一筆記錄範例:', data.documents?.[0]);
          
          if (data.documents && data.documents.length > 0) {
            setDocuments((prev) => {
              // 去重：只添加前端狀態中不存在的記錄
              const existingIds = new Set(prev.map(d => d.id));
              const newDocs = data.documents.filter(doc => !existingIds.has(doc.id));
              console.log('📰 [載入] 新增文件數:', newDocs.length);
              return newDocs.length > 0 ? [...newDocs, ...prev] : prev;
            });
            if (!selectedDocId) {
              setSelectedDocId(data.documents[0]?.id || '');
            }
          }
        }
      } catch (error) {
        console.warn('載入新聞記錄失敗:', error);
      }
    };
    loadNewsRecords();
  }, [isAuthenticated]);

  const persistDocTags = async (tagKey, tags) => {
    if (!tagKey) return;
    try {
      await fetch(`${apiBase || ''}/api/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag_key: tagKey, tags }),
      });
    } catch (error) {
      console.warn('標籤保存失敗:', error);
    }
  };

  const persistCustomTags = async (tags) => {
    try {
      await fetch(`${apiBase || ''}/api/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ custom_tags: tags }),
      });
    } catch (error) {
      console.warn('自定義標籤保存失敗:', error);
    }
  };

  const filteredTranslations = selectedDocId
    ? artifacts.translations.filter((item) => (item.sourceDocIds || []).includes(selectedDocId))
    : artifacts.translations;

  const filteredSummaries = selectedDocId
    ? artifacts.summaries.filter((item) => (item.sourceDocIds || []).includes(selectedDocId))
    : artifacts.summaries;

  // Load preloaded PDF documents on startup (only once)
  useEffect(() => {
    let isMounted = true;
    const loadPreloadedDocs = async () => {
      try {
        const response = await fetch(`${apiBase || ''}/api/documents/preloaded`);
        if (!response.ok || !isMounted) return;
        const data = await response.json();
        
        // 獲取已刪除的文件 ID 列表
        const deletedIds = JSON.parse(localStorage.getItem('deletedDocIds') || '[]');
        console.log('📄 [預載] 已刪除ID列表:', deletedIds);
        
        const pdfDocs = (data.documents || [])
          .filter(doc => !deletedIds.includes(doc.id))  // 過濾已刪除的文件
          .map((doc) => ({
            id: doc.id,
            name: doc.name,
            type: doc.type,
            pages: doc.pages ?? '-',
            tag_key: doc.tag_key || doc.id,
            tags: Array.isArray(doc.tags) ? doc.tags : [],
            content: doc.preview || '',
            image: '',
            image_mime: '',
            status: doc.status,
            message: doc.message,
            source: 'preloaded',
          }));
        
        console.log('📄 [預載] 過濾後文件數:', pdfDocs.length);
        
        if (pdfDocs.length > 0 && isMounted) {
          setDocuments((prev) => {
            // Deduplicate by ID
            const existingIds = new Set(prev.map((d) => d.id).filter(Boolean));
            const existingKeys = new Set(
              prev
                .filter((d) => d.source === 'preloaded')
                .map((d) => `${(d.name || '').toLowerCase()}::${(d.type || '').toLowerCase()}`)
            );
            const newDocs = pdfDocs.filter((doc) => {
              const key = `${(doc.name || '').toLowerCase()}::${(doc.type || '').toLowerCase()}`;
              const idOk = doc.id ? !existingIds.has(doc.id) : true;
              const keyOk = !existingKeys.has(key);
              return idOk && keyOk;
            });
            return newDocs.length > 0 ? [...prev, ...newDocs] : prev;
          });
        }
      } catch (error) {
        console.error('載入預加載文檔失敗:', error);
      }
    };
    loadPreloadedDocs();
    return () => { isMounted = false; };
  }, []);

  useEffect(() => {
    let isMounted = true;
    const loadTags = async () => {
      try {
        const response = await fetch(`${apiBase || ''}/api/tags`);
        if (!response.ok || !isMounted) return;
        const data = await response.json();
        if (Array.isArray(data.custom_tags) && isMounted) {
          setCustomTags(data.custom_tags);
        }
        const docTags = data.doc_tags || {};
        if (isMounted && docTags && typeof docTags === 'object') {
          setDocuments((prev) =>
            prev.map((doc) => {
              const tagKey = doc.tag_key || doc.id;
              const savedTags = docTags[tagKey];
              if (!Array.isArray(savedTags)) return doc;
              return { ...doc, tags: savedTags };
            })
          );
        }
      } catch (error) {
        console.warn('載入標籤失敗:', error);
      }
    };
    loadTags();
    return () => { isMounted = false; };
  }, []);

  // Ensure activeTranslationIndex is within bounds for selected document
  useEffect(() => {
    if (filteredTranslations.length === 0) {
      if (activeTranslationIndex !== 0) {
        setActiveTranslationIndex(0);
      }
      return;
    }
    if (activeTranslationIndex >= filteredTranslations.length) {
      setActiveTranslationIndex(filteredTranslations.length - 1);
    }
  }, [filteredTranslations.length, activeTranslationIndex]);

  const fileInputRef = useRef(null);

  // Get active artifact based on tab
  const getActiveArtifact = () => {
    if (activeTab === 'documents') {
      return { output: '' };
    }
    if (activeTab === 'translation') {
      if (filteredTranslations.length === 0) {
        return emptyTranslation;
      }
      return filteredTranslations[activeTranslationIndex] || filteredTranslations[0];
    }
    if (activeTab === 'summary') {
      if (filteredSummaries.length === 0) {
        return emptySummary;
      }
      return filteredSummaries[filteredSummaries.length - 1];
    }
    return artifacts[activeTab];
  };

  const activeArtifact = getActiveArtifact();
  const hasRouting = routingSteps.length > 0;
  const latestRouting = hasRouting ? routingSteps[routingSteps.length - 1] : null;
  const latestRoutingStatus = latestRouting
    ? statusMeta[latestRouting.status] || null
    : null;
  const isStatusLike = (value, statusLabel) => {
    if (!value) return false;
    const normalized = value.trim();
    if (!normalized) return false;
    const statusWords = ['進行中', '正在進行中', '等待中', '完成', '已完成'];
    if (statusLabel && normalized === statusLabel.trim()) return true;
    return statusWords.some((word) => normalized.includes(word));
  };
  const routingSummaryText = (() => {
    if (!latestRouting) return '尚未啟動';
    const labelText = (latestRouting.label || '').trim();
    const etaText = (latestRouting.eta || '').trim();
    const statusLabel = (latestRoutingStatus?.label || '').trim();
    const labelIsStatus = isStatusLike(labelText, statusLabel);
    const etaIsStatus = isStatusLike(etaText, statusLabel);
    let text = labelIsStatus ? '' : labelText;
    if (etaText && !etaIsStatus && etaText !== labelText) {
      text = text ? `${text} · ${etaText}` : etaText;
    }
    return text || '—';
  })();

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  // Tag management functions
  const handleToggleTag = async (docId, tag) => {
    setDocuments((prev) => {
      let updatedTags = null;
      let tagKey = '';
      const next = prev.map((doc) => {
        if (doc.id !== docId) return doc;
        const tags = doc.tags || [];
        const hasTag = tags.includes(tag);
        updatedTags = hasTag ? tags.filter((t) => t !== tag) : [...tags, tag];
        tagKey = doc.tag_key || doc.id;
        return {
          ...doc,
          tags: updatedTags,
        };
      });
      if (updatedTags && tagKey) {
        persistDocTags(tagKey, updatedTags);
        // 同時更新數據庫
        fetch(`${apiBase || ''}/api/news/records/${docId}/tags`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updatedTags),
        }).catch(err => console.warn('更新標籤失敗:', err));
      }
      return next;
    });
  };

  const handleAddCustomTag = () => {
    const trimmed = newTagInput.trim();
    if (!trimmed) return;
    if (!customTags.includes(trimmed)) {
      const nextTags = [...customTags, trimmed];
      setCustomTags(nextTags);
      persistCustomTags(nextTags);
    }
    if (editingDocId) {
      handleToggleTag(editingDocId, trimmed);
    }
    setNewTagInput('');
  };

  const handleToggleEditTags = (docId) => {
    setEditingDocId((prev) => (prev === docId ? '' : docId));
  };

  const handleDeleteDoc = async (docId) => {
    console.log('🗑️ [刪除函數被呼叫] docId:', docId);
    
    if (!docId) return;
    const doc = documents.find((d) => d.id === docId);
    if (!doc) {
      console.log('🗑️ [刪除] 找不到文件');
      return;
    }
    
    const docName = doc.name || '文件';
    console.log('🗑️ [刪除] 準備刪除:', { id: docId, name: docName, source: doc.source, type: doc.type });
    
    if (!window.confirm(`確定要刪除「${docName}」嗎？`)) {
      console.log('🗑️ [刪除] 使用者取消');
      return;
    }

    try {
      // 根據來源決定是否需要呼叫後端 API
      const source = doc.source || 'news';
      console.log('🗑️ [刪除] 文件來源:', source);
      
      if (source === 'news' || source === 'research') {
        // 新聞記錄：從資料庫刪除
        console.log('🗑️ [刪除] 呼叫後端 API:', `${apiBase || ''}/api/news/records/${docId}`);
        const response = await fetch(`${apiBase || ''}/api/news/records/${docId}`, {
          method: 'DELETE',
        });
        
        console.log('🗑️ [刪除] 後端回應狀態:', response.status, response.ok);
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error('🗑️ [刪除] 後端錯誤:', errorText);
          alert('刪除失敗');
          return;
        }
        
        const result = await response.json();
        console.log('🗑️ [刪除] 後端回應:', result);
      } else if (source === 'preloaded' || source === 'uploaded') {
        // 預載文件和上傳文件：記錄到 localStorage，防止重新載入
        const deletedIds = JSON.parse(localStorage.getItem('deletedDocIds') || '[]');
        if (!deletedIds.includes(docId)) {
          deletedIds.push(docId);
          localStorage.setItem('deletedDocIds', JSON.stringify(deletedIds));
          console.log('🗑️ [刪除] 已記錄到 localStorage:', deletedIds.length, '個已刪除ID');
        }
      }
      
      // 從前端狀態中移除
      setDocuments((prev) => {
        const next = prev.filter((d) => d.id !== docId);
        console.log('🗑️ [刪除] 前端狀態更新，剩餘文件數:', next.length);
        // Update selection if the current one was removed
        if (selectedDocId === docId) {
          setSelectedDocId(next[0]?.id || '');
        }
        if (editingDocId === docId) {
          setEditingDocId('');
        }
        return next;
      });
      
      console.log('✅ [刪除] 刪除完成');
    } catch (error) {
      console.error('❌ [刪除] 刪除記錄失敗:', error);
      alert('刪除時發生錯誤');
    }
  };

  const handleUploadFiles = async (event) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    setErrorMessage('');

    try {
      const formData = new FormData();
      files.forEach((file) => formData.append('files', file));

      const response = await fetch(`${apiBase || ''}/api/documents`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || '文件上傳失敗');
      }

      const nextDocs = (data.documents || []).map((doc) => ({
        id: doc.id || createId(),
        name: doc.name || '未命名',
        type: doc.type || 'FILE',
        pages: doc.pages ?? '-',
        tag_key: doc.tag_key || doc.id,
        tags: Array.isArray(doc.tags) ? doc.tags : [],
        content: doc.preview || '',
        image: doc.image || '',
        image_mime: doc.image_mime || '',
        status: doc.status,
        message: doc.message,
        source: 'uploaded',
      }));

      if (!nextDocs.length) {
        throw new Error('未取得文件資訊');
      }

      setDocuments((prev) => [...nextDocs, ...prev]);
      setSelectedDocId(nextDocs[0]?.id || selectedDocId);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? `上傳失敗: ${error.message}` : '上傳失敗，請稍後再試。'
      );
    } finally {
      event.target.value = '';
    }
  };


  // Download artifact output as file
  const handleDownloadOutput = () => {
    const content = activeArtifact.output;
    if (!content) {
      setErrorMessage('尚無內容可下載');
      return;
    }
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${activeTab}-${caseId}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Create new case (reset all state)
  const handleNewCase = () => {
    const hasContent = messages.length > 0 || artifacts.summaries.length > 0 || artifacts.translations.length > 0 || artifacts.memo.output;
    if (hasContent) {
      if (!window.confirm('確定要新增案件嗎？目前的對話和產出將會清空。')) {
        return;
      }
    }
    setMessages([]);
    setRoutingSteps([]);
    setCurrentStage('');
    setCompletedStages([]);
    setArtifacts({
      summaries: [],
      translations: [],
      memo: { output: '', sections: [], recommendation: '', conditions: '' },
    });
    setActiveTranslationIndex(0);
    setErrorMessage('');
    setComposerText('');
    setReasoningSummary('');
  };

  // Export all artifacts as a package
  const handleExportPackage = () => {
    const packageContent = {
      caseId,
      exportTime: new Date().toISOString(),
      summary: artifacts.summaries[artifacts.summaries.length - 1] || emptySummary,
      summaries: artifacts.summaries,
      translations: artifacts.translations,
      memo: artifacts.memo,
      documents: documents.map((d) => ({ name: d.name, type: d.type, tags: d.tags })),
    };
    const blob = new Blob([JSON.stringify(packageContent, null, 2)], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `artifacts-${caseId}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // 開啟匯出對話框
  const handleOpenExportModal = (doc) => {
    setCurrentDocForExport(doc);
    setShowExportModal(true);
  };

  // 匯出並發送郵件
  const handleExportAndSend = async () => {
    if (!currentDocForExport) {
      setErrorMessage('未選擇文件');
      return;
    }

    if (!recipientEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipientEmail)) {
      setErrorMessage('請輸入有效的郵箱地址');
      return;
    }

    setIsExporting(true);
    setErrorMessage('');

    try {
      const response = await fetch(`${apiBase || ''}/api/export-news`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_id: currentDocForExport.id,
          document_name: currentDocForExport.name,
          document_content: currentDocForExport.content || '',
          recipient_email: recipientEmail,
          subject: '東南亞新聞輿情報告',
        }),
      });

      const result = await response.json();

      if (result.success) {
        setShowExportModal(false);
        setRecipientEmail('');
        setCurrentDocForExport(null);
        alert(`✅ 已成功將 ${result.count} 筆新聞匯出並發送至 ${recipientEmail}`);
      } else {
        setErrorMessage(result.error || '匯出失敗');
      }
    } catch (error) {
      console.error('匯出錯誤:', error);
      setErrorMessage('匯出過程中發生錯誤，請稍後再試');
    } finally {
      setIsExporting(false);
    }
  };

  // 切換新聞選中狀態
  const handleToggleNewsSelection = (docId) => {
    setSelectedNewsIds((prev) => {
      if (prev.includes(docId)) {
        return prev.filter(id => id !== docId);
      } else {
        return [...prev, docId];
      }
    });
  };

  // 全選/全不選
  const handleToggleSelectAll = () => {
    const exportableDocs = documents.filter(
      (doc) => (doc.type === 'RESEARCH' || doc.type === 'NEWS') && doc.content
    );
    if (selectedNewsIds.length === exportableDocs.length) {
      setSelectedNewsIds([]);
    } else {
      setSelectedNewsIds(exportableDocs.map(doc => doc.id));
    }
  };

  // 開啟批次匯出對話框
  const handleOpenBatchExport = () => {
    if (selectedNewsIds.length === 0) {
      alert('請先勾選要匯出的新聞');
      return;
    }
    setShowBatchExportModal(true);
  };

  // 批次匯出並發送郵件
  const handleBatchExportAndSend = async () => {
    if (selectedNewsIds.length === 0) {
      setErrorMessage('未選擇新聞');
      return;
    }

    if (!batchRecipientEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(batchRecipientEmail)) {
      setErrorMessage('請輸入有效的郵箱地址');
      return;
    }

    setIsBatchExporting(true);
    setErrorMessage('');

    try {
      // 獲取所有選中的文件
      const selectedDocs = documents.filter(doc => selectedNewsIds.includes(doc.id));
      
      const response = await fetch(`${apiBase || ''}/api/export-news-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          documents: selectedDocs.map(doc => ({
            id: doc.id,
            name: doc.name,
            content: doc.content || '',
          })),
          recipient_email: batchRecipientEmail,
          subject: '東南亞新聞輿情報告（批次匯出）',
        }),
      });

      const result = await response.json();

      if (result.success) {
        setShowBatchExportModal(false);
        setBatchRecipientEmail('');
        setSelectedNewsIds([]);
        alert(`✅ 已成功將 ${result.count} 筆新聞匯出並發送至 ${batchRecipientEmail}`);
      } else {
        setErrorMessage(result.error || '批次匯出失敗');
      }
    } catch (error) {
      console.error('批次匯出錯誤:', error);
      setErrorMessage('批次匯出過程中發生錯誤，請稍後再試');
    } finally {
      setIsBatchExporting(false);
    }
  };

  // 批量刪除新聞
  const handleBatchDelete = async () => {
    if (selectedNewsIds.length === 0) {
      alert('請先勾選要刪除的新聞');
      return;
    }

    const selectedDocs = documents.filter(doc => selectedNewsIds.includes(doc.id));
    const confirmMessage = `確定要刪除 ${selectedNewsIds.length} 筆新聞嗎？\n\n${selectedDocs.map(doc => '• ' + doc.name).slice(0, 5).join('\n')}${selectedDocs.length > 5 ? '\n...' : ''}`;
    
    if (!window.confirm(confirmMessage)) {
      return;
    }

    try {
      // 分類文件：哪些需要呼叫 API，哪些只需前端移除
      const newsRecordIds = selectedDocs
        .filter(doc => doc.source === 'news' || doc.source === 'research')
        .map(doc => doc.id);
      
      const preloadedIds = selectedDocs
        .filter(doc => doc.source === 'preloaded' || doc.source === 'uploaded')
        .map(doc => doc.id);
      
      let successCount = selectedNewsIds.length;
      
      // 只對新聞記錄呼叫刪除 API
      if (newsRecordIds.length > 0) {
        const deletePromises = newsRecordIds.map(docId =>
          fetch(`${apiBase || ''}/api/news/records/${docId}`, {
            method: 'DELETE',
          })
        );

        const results = await Promise.all(deletePromises);
        const apiSuccessCount = results.filter(r => r.ok).length;
        
        if (apiSuccessCount < newsRecordIds.length) {
          successCount -= (newsRecordIds.length - apiSuccessCount);
        }
      }
      
      // 預載文件：記錄到 localStorage
      if (preloadedIds.length > 0) {
        const deletedIds = JSON.parse(localStorage.getItem('deletedDocIds') || '[]');
        const updatedIds = [...new Set([...deletedIds, ...preloadedIds])];
        localStorage.setItem('deletedDocIds', JSON.stringify(updatedIds));
        console.log('🗑️ [批次刪除] 已記錄', preloadedIds.length, '個預載文件ID');
      }

      // 從前端狀態中移除已刪除的項目
      setDocuments((prev) => {
        const next = prev.filter((doc) => !selectedNewsIds.includes(doc.id));
        // Update selection if needed
        if (selectedNewsIds.includes(selectedDocId)) {
          setSelectedDocId(next[0]?.id || '');
        }
        return next;
      });

      setSelectedNewsIds([]);
      alert(`✅ 已成功刪除 ${successCount} 筆新聞`);
    } catch (error) {
      console.error('批量刪除錯誤:', error);
      alert('批量刪除時發生錯誤，請稍後再試');
    }
  };

  const handleSend = async () => {
    const trimmed = composerText.trim();
    if (!trimmed || isLoading) return;

    const userMessage = {
      id: createId(),
      role: 'user',
      name: 'User',
      time: nowTime(),
      content: trimmed,
    };

    const outgoingMessages = [...messages, userMessage];

    setMessages(outgoingMessages);
    setComposerText('');
    setIsLoading(true);
    setErrorMessage('');
    setStreamingContent('');
    setRoutingSteps([]);
    setCurrentStage('analyze'); // 送出指示後立即顯示需求分析階段
    setCompletedStages([]);
    setReasoningSummary('');

    try {
      // Build system context for LLM
      const systemContext = {
        case_id: caseId,
        owner_name: ownerName,
        has_summary: artifacts.summaries.length > 0,
        has_translation: artifacts.translations.length > 0,
        has_memo: Boolean(artifacts.memo.output),
        translation_count: artifacts.translations.length,
        selected_doc_id: selectedDocId || null,
        selected_doc_name: documents.find((doc) => doc.id === selectedDocId)?.name || null,
      };

      const response = await fetch(`${apiBase}/api/artifacts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: outgoingMessages.map((item) => ({
            role: item.role,
            content: item.content,
          })),
          documents,
          stream: true,
          system_context: systemContext,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || 'API request failed');
      }

      const contentType = response.headers.get('content-type') || '';
      let data = null;
      let hasRoutingUpdates = false;
      
      const applyRoutingUpdate = (update) => {
        if (!update || !update.id) return;
        
        console.log('🔄 [路由處理] 應用更新:', update);
        
        setRoutingSteps((prev) => {
          const index = prev.findIndex((step) => step.id === update.id);
          if (index >= 0) {
            const next = [...prev];
            next[index] = { ...next[index], ...update };
            console.log('✏️ [路由處理] 更新現有步驟:', next[index]);
            return next;
          }
          console.log('➕ [路由處理] 新增步驟:', update);
          return [...prev, update];
        });
        
        // 根據後端提供的 stage 標記更新階段
        const stage = update.stage;
        const status = update.status || '';
        
        console.log(`📊 [階段判斷] stage: "${stage}", status: "${status}"`);
        
        // 使用後端明確標記的階段
        if (stage) {
          if (stage === 'analyze' && status === 'running') {
            console.log('🎯 [階段追蹤] ✅ 需求分析階段 (TeamRunStarted)');
            setCurrentStage('analyze');
            setCompletedStages([]);
          } else if (stage === 'search' && status === 'running') {
            console.log('🎯 [階段追蹤] ✅ 搜尋資料階段 (TeamRunContent)');
            setCurrentStage('search');
            setCompletedStages(['analyze']);
          } else if (stage === 'process') {
            console.log('🎯 [階段追蹤] ✅ 處理內容階段 (TeamRunContentCompleted)');
            setCurrentStage('process');
            setCompletedStages(['analyze', 'search']);
          } else if (stage === 'complete' && status === 'done') {
            console.log('🎯 [階段追蹤] ✅ 完成階段 (TeamRunCompleted)');
            setCurrentStage('complete');
            setCompletedStages(['analyze', 'search', 'process']);
          }
        }
      };

      if (!contentType.includes('text/event-stream')) {
        // Fallback: handle JSON (e.g., error response) when SSE is not returned
        data = await response.json().catch(() => null);
      } else {
        // Handle SSE streaming
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let accumulatedContent = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;

            try {
              const parsed = JSON.parse(jsonStr);

              // Handle streaming chunks - update routing in real-time
              if (parsed.chunk) {
                accumulatedContent += parsed.chunk;
                setStreamingContent(accumulatedContent);
                continue;
              }

              if (parsed.routing_update) {
                hasRoutingUpdates = true;
                console.log('📍 [即時路由] 收到更新:', parsed.routing_update);
                applyRoutingUpdate(parsed.routing_update);
                continue;
              }

              // 處理 LLM 處理日誌（替代推理摘要）
              if (parsed.log_chunk) {
                setReasoningSummary((prev) => {
                  const updated = prev + parsed.log_chunk + '\n';
                  console.log('📋 [處理日誌]', parsed.log_chunk);
                  return updated;
                });
                continue;
              }

              // 處理完整推理摘要（最終結果）
              if (parsed.reasoning_summary) {
                setReasoningSummary(parsed.reasoning_summary);
                console.log('🧠 [推理完成] 收到完整推理摘要');
                continue;
              }

              // Handle final complete data or done signal
              if (parsed.done) {
                // 任務完成，標記所有階段為完成
                setCurrentStage('complete');
                setCompletedStages(['analyze', 'search', 'process', 'complete']);
                continue;
              }

              if (parsed.error) {
                throw new Error(parsed.error);
              }

              // Final parsed response
              if (parsed.assistant || parsed.summary || parsed.translation || parsed.memo) {
                data = parsed;
              }
            } catch (parseErr) {
              console.warn('Parse error:', parseErr);
            }
          }
        }
      }

      console.log('📦 Received data from API:', data);

      if (!data) {
        throw new Error('No valid response received');
      }

      if (data.error) {
        throw new Error(data.error + (data.detail ? `: ${data.detail}` : ''));
      }

      if (Array.isArray(data.documents_update) && data.documents_update.length > 0) {
        setDocuments((prev) =>
          prev.map((doc) => {
            const update = data.documents_update.find((item) => item.id === doc.id);
            if (!update) return doc;
            const isImageDoc = Boolean(doc.image || update.image || (doc.type || '').toLowerCase().match(/png|jpg|jpeg|webp|gif/));
            // Only apply OCR updates to image-based documents to avoid overwriting text docs
            if (!isImageDoc) {
              return doc;
            }
            return {
              ...doc,
              content: update.content || doc.content,
              pages: update.pages ?? doc.pages,
              status: update.status || doc.status,
              message: update.message || doc.message,
              tags: Array.isArray(update.tags) ? update.tags : doc.tags,
              tag_key: update.tag_key || doc.tag_key,
            };
          })
        );
      }

      if (Array.isArray(data.documents_append) && data.documents_append.length > 0) {
        const appendedDocs = data.documents_append.map((doc) => ({
          id: doc.id || createId(),
          name: doc.name || '未命名',
          type: doc.type || 'NEWS',
          pages: doc.pages ?? '-',
          tags: Array.isArray(doc.tags) ? doc.tags : [],
          content: doc.content || doc.preview || '',
          image: doc.image || '',
          image_mime: doc.image_mime || '',
          tag_key: doc.tag_key || doc.id,
          status: doc.status || 'indexed',
          message: doc.message || '',
          source: doc.source || 'news',
          publish_date: doc.publish_date || '',
          url: doc.url || '',
        }));

        setDocuments((prev) => {
          const existingIds = new Set(prev.map((doc) => doc.id));
          const uniqueDocs = appendedDocs.filter((doc) => !existingIds.has(doc.id));
          return uniqueDocs.length > 0 ? [...uniqueDocs, ...prev] : prev;
        });
      }

      // Update artifacts
      if (data.summary || data.translation || data.memo) {
        const resolveSourceDocIds = (payload) => {
          const ids = Array.isArray(payload?.source_doc_ids)
            ? payload.source_doc_ids
            : payload?.source_doc_id
              ? [payload.source_doc_id]
              : [];
          const names = Array.isArray(payload?.source_doc_names)
            ? payload.source_doc_names
            : payload?.source_doc_name
              ? [payload.source_doc_name]
              : [];

          const resolvedIds = ids
            .map((id) => documents.find((doc) => doc.id === id)?.id)
            .filter(Boolean);

          if (resolvedIds.length > 0) {
            return resolvedIds;
          }

          if (names.length === 0) {
            return [];
          }

          const normalizedNames = names
            .map((name) => (name || '').trim())
            .filter(Boolean);
          if (normalizedNames.length === 0) {
            return [];
          }

          return documents
            .filter((doc) =>
              normalizedNames.some(
                (name) => name.toLowerCase() === (doc.name || '').toLowerCase()
              )
            )
            .map((doc) => doc.id);
        };

        const summaryDocIds = resolveSourceDocIds(data.summary);
        const translationDocIds = resolveSourceDocIds(data.translation);

        setArtifacts((prev) => {
          let summaries = prev.summaries;
          const hasSummaryPayload = Boolean(
            data.summary?.output ||
              data.summary?.borrower?.name ||
              data.summary?.borrower?.description ||
              data.summary?.borrower?.rating ||
              (data.summary?.metrics || []).length ||
              (data.summary?.risks || []).length
          );

          if (data.summary && hasSummaryPayload) {
            const summaryEntry = {
              id: createId(),
              timestamp: Date.now(),
              sourceDocIds: summaryDocIds,
              output: data.summary.output || '',
              borrower: data.summary.borrower || emptySummary.borrower,
              metrics: data.summary.metrics || [],
              risks: data.summary.risks || [],
            };
            summaries = [...prev.summaries, summaryEntry];
          }

          const newArtifacts = {
            summaries,
            translations: prev.translations,
            memo: {
              ...prev.memo,
              output: data.memo?.output || prev.memo.output,
              sections: data.memo?.sections || prev.memo.sections,
              recommendation: data.memo?.recommendation || prev.memo.recommendation,
              conditions: data.memo?.conditions || prev.memo.conditions,
            },
          };

          // Add new translation version if present
          if (data.translation && (data.translation.output || data.translation.clauses?.length > 0)) {
            const primaryTranslationDocId =
              translationDocIds.length === 1 ? translationDocIds[0] : null;
            const docTranslationCount = primaryTranslationDocId
              ? prev.translations.filter((item) =>
                (item.sourceDocIds || []).includes(primaryTranslationDocId)
              ).length
              : prev.translations.length;
            const newTranslation = {
              id: createId(),
              timestamp: Date.now(),
              title: `翻譯 #${docTranslationCount + 1}`,
              sourceDocIds: translationDocIds,
              output: data.translation.output || '',
              clauses: data.translation.clauses || [],
            };
            newArtifacts.translations = [...prev.translations, newTranslation];
            setActiveTranslationIndex(
              primaryTranslationDocId ? docTranslationCount : newArtifacts.translations.length - 1
            );
          }

          return newArtifacts;
        });
      }

      if (data.reasoning_summary) {
        setReasoningSummary(data.reasoning_summary);
      }

      // Update routing
      if (!hasRoutingUpdates && Array.isArray(data.routing)) {
        setRoutingSteps(
          data.routing.map((step) => ({
            id: step.id || createId(),
            label: step.label || '任務更新',
            status: step.status || 'done',
            eta: step.eta || '完成',
          }))
        );
        // 任務完成，標記所有階段為完成
        setCurrentStage('complete');
        setCompletedStages(['init', 'analyze', 'search', 'process', 'generate']);
      } else if (!hasRoutingUpdates) {
        setRoutingSteps([]);
      }

      // Add assistant message
      const assistantMessage = {
        id: createId(),
        role: 'assistant',
        name: 'LLM',
        time: nowTime(),
        content: data.assistant?.content || '已完成處理。',
        bullets: data.assistant?.bullets,
      };

      setMessages((prev) => [...prev, assistantMessage]);
      
      // 標記所有階段為完成
      setCurrentStage('complete');
      setCompletedStages(['init', 'analyze', 'search', 'process', 'generate', 'complete']);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? `連線失敗: ${error.message}`
          : '連線失敗，請稍後再試。'
      );
      // 錯誤時也重置進度
      setCurrentStage('');
      setCompletedStages([]);
    } finally {
      setIsLoading(false);
      setStreamingContent('');
    }
  };

  const renderMarkdown = (value) => {
    const safeText =
      typeof value === 'string'
        ? value.trim()
        : value
          ? JSON.stringify(value, null, 2)
          : '';

    return (
      <div className="markdown-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {safeText || '尚未產出，請先在左側送出指示。'}
        </ReactMarkdown>
      </div>
    );
  };

  return (
    <ThemeProvider
      customTheme={{
        primaryColor: '#1f4b6e',
        neutralColor: '#1c1a18',
      }}
    >
      {!isAuthenticated ? (
        <div className="login-container">
          <div className="login-box">
            <div className="login-header">
              <div className="brand-icon" style={{ fontSize: '48px' }}>📰</div>
              <Text as="h1" weight="700" style={{ fontSize: '28px', margin: '16px 0 8px' }}>
                SEA News 東南亞新聞情報系統
              </Text>
              <Text style={{ color: 'var(--muted)', marginBottom: '32px' }}>
                Cathay United Bank
              </Text>
            </div>
            <form onSubmit={handleLogin} className="login-form">
              <div className="login-field">
                <label htmlFor="username" className="login-label">
                  帳號
                </label>
                <input
                  id="username"
                  type="text"
                  className="login-input"
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                  placeholder="請輸入帳號"
                  autoComplete="username"
                  autoFocus
                />
              </div>
              <div className="login-field">
                <label htmlFor="password" className="login-label">
                  密碼
                </label>
                <input
                  id="password"
                  type="password"
                  className="login-input"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="請輸入密碼"
                  autoComplete="current-password"
                />
              </div>
              {loginError && (
                <div className="login-error">
                  {loginError}
                </div>
              )}
              <Button
                type="primary"
                htmlType="submit"
                size="large"
                style={{ width: '100%', marginTop: '8px' }}
              >
                登入
              </Button>
            </form>
          </div>
        </div>
      ) : (
        <div className="artifact-app">
          <header className="artifact-header">
            <div className="brand">
              <div className="brand-icon">
                <Icon icon={Landmark} size="small" />
              </div>
            <div>
              <Text as="h1" weight="700" className="brand-title">
                新聞輿情系統
              </Text>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => {
                localStorage.removeItem('authToken');
                setIsAuthenticated(false);
                setLoginUsername('');
                setLoginPassword('');
              }}
            >
              登出
            </Button>
          </div>

        </header>

        <div className="artifact-shell">
          <section className="panel docs-panel">
            <div className="panel-header">
              <div>
                <Text as="h2" weight="600" className="panel-title">
                  新聞集
                </Text>
              </div>
              <div className="panel-actions">
                {documents.some((doc) => (doc.type === 'RESEARCH' || doc.type === 'NEWS') && doc.content) && (
                  <>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={handleToggleSelectAll}
                    >
                      {selectedNewsIds.length === documents.filter(doc => (doc.type === 'RESEARCH' || doc.type === 'NEWS') && doc.content).length ? '取消全選' : '全選'}
                    </Button>
                    <Button
                      type="primary"
                      size="small"
                      onClick={handleOpenBatchExport}
                      disabled={selectedNewsIds.length === 0}
                    >
                      批量匯出 ({selectedNewsIds.length})
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={handleBatchDelete}
                      disabled={selectedNewsIds.length === 0}
                      style={{ color: '#ff4d4f', borderColor: '#ff4d4f' }}
                    >
                      批量刪除 ({selectedNewsIds.length})
                    </Button>
                  </>
                )}
              </div>
            </div>

            <div className="doc-tray">
              {documents.length > 0 ? (
                <div className="doc-grid">
                  {documents.map((doc) => {
                    const isEditing = editingDocId === doc.id;
                    const isExportable = (doc.type === 'RESEARCH' || doc.type === 'NEWS') && doc.content;
                    const isSelected = selectedNewsIds.includes(doc.id);

                    return (
                      <div
                        key={doc.id}
                        className={`doc-card${doc.id === selectedDocId ? ' is-active' : ''}`}
                        onClick={() => !isEditing && setSelectedDocId(doc.id)}
                      >
                        <div className="doc-card-row">
                          {isExportable && (
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={(e) => {
                                e.stopPropagation();
                                handleToggleNewsSelection(doc.id);
                              }}
                              onClick={(e) => e.stopPropagation()}
                              style={{ marginRight: '8px', cursor: 'pointer' }}
                            />
                          )}
                          <div className="doc-title">{doc.name}</div>
                          <Tag size="small" color="blue">{doc.type}</Tag>
                          {isExportable && (
                            <ActionIcon
                              icon={Download}
                              size="small"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenExportModal(doc);
                              }}
                              title="匯出 Excel 並寄送"
                            />
                          )}
                          <ActionIcon
                            icon={isEditing ? X : Edit3}
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleToggleEditTags(doc.id);
                            }}
                            title={isEditing ? '關閉編輯' : '編輯標籤'}
                          />
                          <ActionIcon
                            icon={Trash}
                            size="small"
                            variant="outlined"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteDoc(doc.id);
                            }}
                            title="刪除文件"
                          />
                        </div>

                        {isEditing ? (
                          <div className="tag-editor">
                            <div className="tag-section">
                              <div className="tag-section-title">流程狀態</div>
                              <div className="tag-selector">
                                {workflowTags.map((tag) => (
                                  <button
                                    key={tag}
                                    type="button"
                                    className={`tag-option${(doc.tags || []).includes(tag) ? ' is-selected' : ''}`}
                                    onClick={() => handleToggleTag(doc.id, tag)}
                                  >
                                    <Tag size="small" color={tagColors[tag] || 'default'}>
                                      {tag}
                                    </Tag>
                                  </button>
                                ))}
                              </div>
                            </div>

                            <div className="tag-section">
                              <div className="tag-section-title">功能標籤</div>
                              <div className="tag-selector">
                                {functionTags.map((tag) => (
                                  <button
                                    key={tag}
                                    type="button"
                                    className={`tag-option${(doc.tags || []).includes(tag) ? ' is-selected' : ''}`}
                                    onClick={() => handleToggleTag(doc.id, tag)}
                                  >
                                    <Tag size="small" color={tagColors[tag] || 'default'}>
                                      {tag}
                                    </Tag>
                                  </button>
                                ))}
                              </div>
                            </div>

                            {customTags.length > 0 && (
                              <div className="tag-section">
                                <div className="tag-section-title">自定義標籤</div>
                                <div className="tag-selector">
                                  {customTags.map((tag) => (
                                    <button
                                      key={tag}
                                      type="button"
                                      className={`tag-option${(doc.tags || []).includes(tag) ? ' is-selected' : ''}`}
                                      onClick={() => handleToggleTag(doc.id, tag)}
                                    >
                                      <Tag size="small" color="purple">
                                        {tag}
                                      </Tag>
                                    </button>
                                  ))}
                                </div>
                              </div>
                            )}

                            <div className="tag-add">
                              <input
                                type="text"
                                className="tag-input"
                                placeholder="新增自定義標籤..."
                                value={newTagInput}
                                onChange={(e) => setNewTagInput(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    handleAddCustomTag();
                                  }
                                }}
                              />
                              <ActionIcon
                                icon={Plus}
                                size="small"
                                onClick={handleAddCustomTag}
                                disabled={!newTagInput.trim()}
                                title="新增標籤"
                              />
                            </div>
                          </div>
                        ) : (
                          <div className="doc-tags">
                            {doc.tags?.length ? (
                              doc.tags.map((tag) => (
                                <Tag
                                  key={`${doc.id}-${tag}`}
                                  size="small"
                                  color={tagColors[tag] || (customTags.includes(tag) ? 'purple' : 'default')}
                                >
                                  {tag}
                                </Tag>
                              ))
                            ) : (
                              <span className="doc-empty">點擊 ✏️ 編輯標籤</span>
                            )}
                          </div>
                        )}

                        {doc.status === 'error' ? (
                          <div className="doc-empty">解析失敗</div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>

          </section>

          <section className="panel artifact-panel">
            <div className="panel-header">
              <div>
                <Text as="h2" weight="600" className="panel-title">
                  解析作業區
                </Text>
              </div>
              <div className="panel-actions">
                {activeTab === 'memo' ? (
                  <Button type="primary" onClick={handleDownloadOutput}>
                    匯出報告
                  </Button>
                ) : null}
              </div>
            </div>

            <div className="artifact-stack">
              <div className="preview-card">
                <div className="card-head">
                  <div>
                    <Text as="h3" weight="600" className="card-title">
                      文件內容
                    </Text>
                  </div>
                </div>

                <div className="preview-canvas">
                  {activeTab === 'documents' ? (
                    <div className="preview-documents">
                      {(() => {
                        const selectedDoc = documents.find((doc) => doc.id === selectedDocId);
                        if (!selectedDoc) {
                          return <div className="doc-empty">尚未選擇文件</div>;
                        }
                        return (
                          <>
                            <div className="doc-preview-header">
                              <Icon icon={FileText} size="small" />
                              <span className="doc-preview-name">{selectedDoc.name}</span>
                              <Tag size="small" color="blue">{selectedDoc.type}</Tag>
                              <span className="doc-preview-meta">{selectedDoc.pages} 頁</span>
                            </div>
                            {selectedDoc.tags && selectedDoc.tags.length > 0 && (
                              <div className="doc-preview-tags">
                                {selectedDoc.tags.map((tag) => (
                                  <Tag
                                    key={tag}
                                    size="small"
                                    color={tagColors[tag] || (customTags.includes(tag) ? 'purple' : 'default')}
                                  >
                                    {tag}
                                  </Tag>
                                ))}
                              </div>
                            )}
                            <div className="doc-preview-content-full">
                              {selectedDoc.image ? (
                                <img
                                  src={selectedDoc.image}
                                  alt={selectedDoc.name}
                                  className="doc-preview-image"
                                />
                              ) : selectedDoc.content ? (
                                <pre className="doc-preview-text">{selectedDoc.content}</pre>
                              ) : (
                                <div className="no-preview-full">
                                  <Icon icon={FileText} size="large" />
                                  <p>無文字預覽內容</p>
                                  <p className="no-preview-hint">
                                    此 PDF 文件已索引，可透過 RAG 檢索內容
                                  </p>
                                </div>
                              )}
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  ) : (
                    <div className="live-markdown">
                      {isLoading && streamingContent ? (
                        <div className="streaming-wrapper">
                          <div className="streaming-label">正在產生中...</div>
                          <div className="streaming-content">
                            <pre className="streaming-text">{streamingContent}</pre>
                            <span className="streaming-cursor">▊</span>
                          </div>
                        </div>
                      ) : (
                        renderMarkdown(activeArtifact?.output || '')
                      )}
                    </div>
                  )}

                  {activeTab === 'translation' ? (
                    <div className="preview-translation">
                      {filteredTranslations.length > 1 && (
                        <div className="translation-tabs">
                          {filteredTranslations.map((trans, index) => (
                            <button
                              key={trans.id}
                              type="button"
                              className={`translation-tab${index === activeTranslationIndex ? ' is-active' : ''}`}
                              onClick={() => setActiveTranslationIndex(index)}
                            >
                              {trans.title}
                            </button>
                          ))}
                        </div>
                      )}

                      <div className="translation-list">
                        {(activeArtifact.clauses || []).map((pair) => (
                          <div key={pair.id || pair.section} className="translation-block">
                            <div className="translation-label">{pair.section}</div>
                            <div className="translation-columns">
                              <div className="translation-col">
                                <div className="translation-caption">原文</div>
                                <p>{pair.source}</p>
                              </div>
                              <div className="translation-col">
                                <div className="translation-caption">英文</div>
                                <p>{pair.translated}</p>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </section>

          <section className="panel chat-panel">
            <div className="panel-header">
              <div>
                <Text as="h2" weight="600" className="panel-title">
                  新聞檢索
                </Text>
              </div>
              <div className="panel-actions">
                <Tag size="small" variant="borderless">
                  案件: {caseId}
                </Tag>
                
              </div>
            </div>

            <div className="chat-stream">
              {messages.map((message, index) => (
                <div
                  key={message.id}
                  className={`message ${
                    message.role === 'user' ? 'is-user' : 'is-assistant'
                  }`}
                  style={{ '--delay': `${index * 120}ms` }}
                >
                  <div className="message-avatar">
                    {message.role === 'user' ? 'User' : 'AI'}
                  </div>
                  <div className="message-bubble">
                    <div className="message-meta">
                      <span className="message-name">{message.name}</span>
                      <span className="message-time">{message.time}</span>
                    </div>
                    <p className="message-text">{message.content}</p>
                    {message.bullets ? (
                      <ul className="message-list">
                        {message.bullets.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    ) : null}
                    {message.attachment ? (
                      <div className="message-attachment">
                        <div className="attachment-title">
                          {message.attachment.title}
                        </div>
                        <div className="attachment-detail">
                          {message.attachment.detail}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
              
              {/* 流式內容顯示 */}
              {isLoading && streamingContent && (
                <div className="message is-assistant is-streaming">
                  <div className="message-avatar">AI</div>
                  <div className="message-bubble">
                    <div className="message-meta">
                      <span className="message-name">助理</span>
                      <span className="message-time">{nowTime()}</span>
                    </div>
                    <div className="streaming-content">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {streamingContent}
                      </ReactMarkdown>
                      <span className="typing-cursor">▋</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="routing-panel">
              <div className="routing-header">
                <div className="tray-title">
                  <Icon icon={ListChecks} size="small" />
                  <span>任務路由</span>
                </div>
              </div>
              
              {/* 顯示預定義的任務階段 */}
              <div className="routing-stages">
                {predefinedStages.map((stage, index) => {
                  const isCompleted = completedStages.includes(stage.id);
                  const isCurrent = currentStage === stage.id;
                  const isPending = !isCompleted && !isCurrent;
                  
                  return (
                    <div 
                      key={stage.id} 
                      className={`routing-stage ${
                        isCompleted ? 'is-completed' : 
                        isCurrent ? 'is-current' : 
                        'is-pending'
                      }`}
                    >
                      <div className="stage-indicator">
                        <div className="stage-number">{stage.order}</div>
                        {index < predefinedStages.length - 1 && (
                          <div className="stage-connector"></div>
                        )}
                      </div>
                      <div className="stage-label">{stage.label}</div>
                    </div>
                  );
                })}
              </div>
              
              {/* 處理日誌區域（固定高度） */}
              {reasoningSummary ? (
                <div className="routing-reasoning">
                  
                  <div className="routing-reasoning-text" ref={logContainerRef}>{reasoningSummary}</div>
                </div>
              ) : null}
            </div>

            <div className="chat-composer">
              <TextArea
                rows={3}
                value={composerText}
                onChange={(event) => setComposerText(event.target.value)}
                onKeyDown={(event) => {
                  const isComposing =
                    event.isComposing || (event.nativeEvent && event.nativeEvent.isComposing);
                  if (isComposing) return;
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="輸入問題，例如：最近有哪些關於越南的經濟新聞？"
              />
              {errorMessage ? <div className="error-banner">{errorMessage}</div> : null}
              <div className="composer-actions">
                
                <Button icon={ArrowUpRight} type="primary" onClick={handleSend} disabled={isLoading}>
                  {isLoading ? '產生中...' : '送出指示'}
                </Button>
              </div>
            </div>
          </section>
        </div>
        
        {/* 匯出彈窗 */}
        {showExportModal && (
          <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
          onClick={() => setShowExportModal(false)}
        >
          <div 
            style={{
              backgroundColor: 'white',
              borderRadius: '8px',
              padding: '24px',
              minWidth: '400px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <Text as="h3" weight="600" style={{ marginBottom: '16px' }}>
              匯出並寄送新聞報告
            </Text>
            {currentDocForExport && (
              <Text size="small" style={{ color: '#6c757d', marginBottom: '16px' }}>
                文件：{currentDocForExport.name}
              </Text>
            )}
            <div style={{ marginBottom: '16px' }}>
              <Text size="small" weight="500" style={{ marginBottom: '8px', display: 'block' }}>
                收件人郵箱
              </Text>
              <input
                type="email"
                value={recipientEmail}
                onChange={(e) => setRecipientEmail(e.target.value)}
                placeholder="請輸入收件人郵箱地址"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #d9d9d9',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
            </div>
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <Button
                variant="outlined"
                onClick={() => {
                  setShowExportModal(false);
                  setRecipientEmail('');
                }}
                disabled={isExporting}
              >
                取消
              </Button>
              <Button
                type="primary"
                onClick={handleExportAndSend}
                disabled={isExporting || !recipientEmail.trim()}
              >
                {isExporting ? '處理中...' : '寄送'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 批次匯出彈窗 */}
      {showBatchExportModal && (
        <div 
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
          onClick={() => setShowBatchExportModal(false)}
        >
          <div 
            style={{
              backgroundColor: 'white',
              borderRadius: '8px',
              padding: '24px',
              minWidth: '450px',
              maxWidth: '600px',
              maxHeight: '80vh',
              overflow: 'auto',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <Text as="h3" weight="600" style={{ marginBottom: '16px' }}>
              批次匯出新聞報告
            </Text>
            <div style={{ marginBottom: '16px' }}>
              <Text size="small" weight="500" style={{ marginBottom: '8px', display: 'block' }}>
                已選擇 {selectedNewsIds.length} 筆新聞
              </Text>
              <div style={{ 
                maxHeight: '150px', 
                overflow: 'auto', 
                padding: '12px', 
                backgroundColor: '#f5f5f5', 
                borderRadius: '4px',
                fontSize: '13px'
              }}>
                {documents
                  .filter(doc => selectedNewsIds.includes(doc.id))
                  .map(doc => (
                    <div key={doc.id} style={{ padding: '4px 0' }}>
                      ✓ {doc.name}
                    </div>
                  ))
                }
              </div>
            </div>
            <div style={{ marginBottom: '16px' }}>
              <Text size="small" weight="500" style={{ marginBottom: '8px', display: 'block' }}>
                收件人郵箱
              </Text>
              <input
                type="email"
                value={batchRecipientEmail}
                onChange={(e) => setBatchRecipientEmail(e.target.value)}
                placeholder="請輸入收件人郵箱地址"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  border: '1px solid #d9d9d9',
                  borderRadius: '4px',
                  fontSize: '14px'
                }}
              />
            </div>
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <Button
                variant="outlined"
                onClick={() => {
                  setShowBatchExportModal(false);
                  setBatchRecipientEmail('');
                }}
                disabled={isBatchExporting}
              >
                取消
              </Button>
              <Button
                type="primary"
                onClick={handleBatchExportAndSend}
                disabled={isBatchExporting || !batchRecipientEmail.trim()}
              >
                {isBatchExporting ? '處理中...' : '批次寄送'}
              </Button>
            </div>
          </div>
        </div>
      )}
      </div>
      )}
    </ThemeProvider>
  );
}
