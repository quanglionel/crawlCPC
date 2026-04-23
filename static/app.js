document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("crawl-form");
  const submitButton = document.getElementById("submit_button");
  const sourceSelect = document.getElementById("selected_source_key");
  const sourceHint = document.getElementById("selected_source_hint");
  const crawlJobPanel = document.getElementById("crawl_job_panel");
  const crawlJobText = document.getElementById("crawl_job_text");
  const crawlJobMeta = document.getElementById("crawl_job_meta");
  const crawlJobProgress = document.getElementById("crawl_job_progress");
  const translationToggle = document.getElementById("translation_toggle");
  const translationNotice = document.getElementById("translation_notice");
  const articleList = document.getElementById("article_list");
  const sources = window.SOURCE_CATALOG || [];
  const presetLabels = window.PRESET_LABELS || {};
  const sourceLookup = Object.fromEntries(sources.map((source) => [source.source_key, source]));
  const allSourcesKey = "__all__";
  let crawlJobPollTimer = null;
  let articleCards = Array.from(document.querySelectorAll(".article-card"));
  const renderedArticleUrls = new Set(articleCards.map((card) => card.dataset.articleUrl || "").filter(Boolean));
  const keepAliveIntervalMs = 4 * 60 * 1000;

  const pingHealthCheck = () => {
    fetch("/healthz", {
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).catch(() => {});
  };

  window.setInterval(pingHealthCheck, keepAliveIntervalMs);

  const updateSourceHint = (source) => {
    if (!sourceHint) {
      return;
    }

    if (!source) {
      if (sourceSelect && sourceSelect.value === allSourcesKey) {
        sourceHint.textContent = "Se crawl tat ca nguon da luu va chi giu bai trong 24h gan nhat tinh tu luc bam crawl.";
        return;
      }

      sourceHint.textContent = "Chọn một nguồn đã lưu để chạy. Toàn bộ thiết lập crawl sẽ được nạp tự động từ nguồn đó.";
      return;
    }

    const preset = presetLabels[source.preset_path] || source.preset_path || "chưa có preset";
    const output = source.output || "chưa có output";
    sourceHint.textContent = `${source.target_url} · preset ${preset} · output ${output}`;
  };

  const syncSourceDefaults = () => {
    if (!sourceSelect) {
      return;
    }

    const source = sourceLookup[sourceSelect.value];
    updateSourceHint(source);
  };

  if (sourceSelect) {
    sourceSelect.addEventListener("change", () => syncSourceDefaults());
    syncSourceDefaults();
  }

  if (form && submitButton) {
    form.addEventListener("submit", () => {
      submitButton.disabled = true;
      if (sourceSelect && sourceSelect.value === allSourcesKey) {
        submitButton.textContent = "Dang xep lich crawl...";
      } else {
        submitButton.textContent = "Đang crawl...";
      }
      document.body.classList.add("is-loading");
    });
  }

  const clipText = (value, maxLength = 420) => {
    const text = String(value || "");
    if (text.length <= maxLength) {
      return { text, truncated: false };
    }
    return { text: text.slice(0, maxLength), truncated: true };
  };

  const setCardDataset = (card, article) => {
    const originalContent = clipText(article.content || "");
    card.dataset.articleUrl = article.url || "";
    card.dataset.sourceKey = article.source_key || "";
    card.dataset.sourceName = article.source_name || "All Sources";
    card.dataset.publishedAt = article.published_at || "";
    card.dataset.hasVi = article.display_language === "vi" ? "true" : "false";
    card.dataset.originalTitle = article.title || article.url || "";
    card.dataset.originalSummary = article.summary || "";
    card.dataset.originalDate = article.published_at || "Chua co ngay dang";
    card.dataset.originalContent = originalContent.text;
    card.dataset.originalContentTruncated = originalContent.truncated ? "true" : "false";
    card.dataset.viTitle = article.display_title || "";
    card.dataset.viSummary = article.display_summary || "";
    card.dataset.viDate = article.display_published_at || "";
    card.dataset.viContent = article.display_content || "";
    card.dataset.viContentTruncated = article.display_content_truncated ? "true" : "false";
  };

  const appendTextNode = (parent, tagName, className, text) => {
    const node = document.createElement(tagName);
    if (className) {
      node.className = className;
    }
    node.textContent = text || "";
    parent.appendChild(node);
    return node;
  };

  const createArticleCard = (article) => {
    const card = document.createElement("article");
    card.className = `article-card${article.error ? " is-error" : ""}`;
    setCardDataset(card, article);

    const meta = document.createElement("div");
    meta.className = "article-meta";
    appendTextNode(meta, "span", "", card.dataset.sourceName);
    const date = appendTextNode(meta, "span", "", "");
    date.dataset.articleField = "date";
    appendTextNode(meta, "span", "", article.author || "Khong ro tac gia");
    const badge = appendTextNode(meta, "span", "translation-badge", "Ban dich tieng Viet");
    badge.dataset.translationBadge = "";
    badge.hidden = true;
    card.appendChild(meta);

    const title = appendTextNode(card, "h3", "", "");
    title.dataset.articleField = "title";
    const summary = appendTextNode(card, "p", "article-summary", "");
    summary.dataset.articleField = "summary";
    const content = appendTextNode(card, "p", "article-content", "");
    content.dataset.articleField = "content";

    if (article.translation_error) {
      appendTextNode(card, "p", "article-error", `Khong dich duoc bai nay: ${article.translation_error}`);
    }
    if (article.error) {
      appendTextNode(card, "p", "article-error", article.error);
    }

    if (article.display_language === "vi") {
      const details = document.createElement("details");
      details.className = "original-view";
      details.dataset.originalView = "";
      details.hidden = true;
      appendTextNode(details, "summary", "", "Xem nguyen ban");
      appendTextNode(details, "h4", "", article.title || article.url || "");
      if (article.summary) {
        appendTextNode(details, "p", "", article.summary);
      }
      if (article.content) {
        const originalContent = clipText(article.content);
        appendTextNode(details, "p", "", `${originalContent.text}${originalContent.truncated ? "..." : ""}`);
      }
      card.appendChild(details);
    }

    const actions = document.createElement("div");
    actions.className = "article-actions";
    const link = document.createElement("a");
    link.href = article.url || "#";
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "Mo bai goc";
    actions.appendChild(link);
    card.appendChild(actions);
    return card;
  };

  const appendLiveArticles = (articles) => {
    if (!articleList || !Array.isArray(articles) || !articles.length) {
      return;
    }

    let added = 0;
    articles.forEach((article) => {
      const articleUrl = String(article.url || "");
      if (!articleUrl || renderedArticleUrls.has(articleUrl)) {
        return;
      }
      const card = createArticleCard(article);
      articleList.appendChild(card);
      articleCards.push(card);
      renderedArticleUrls.add(articleUrl);
      added += 1;
    });

    if (!added) {
      return;
    }
    ensureSourceFilterOptions();
    applyTranslationToggle();
    applyResultFilters();
  };

  const renderCrawlJob = (job) => {
    if (!crawlJobPanel || !job) {
      return;
    }

    crawlJobPanel.hidden = false;
    appendLiveArticles(job.articles || []);
    const total = Number(job.source_count || 0);
    const processed = Number(job.processed_sources || 0);
    const progress = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;

    if (crawlJobProgress) {
      crawlJobProgress.value = progress;
    }

    const currentSource = (job.current_source || "").trim();
    const status = (job.status || "").trim();
    if (status === "running") {
      if (crawlJobText) {
        crawlJobText.textContent = currentSource
          ? `Dang crawl: ${currentSource}. Bai moi se hien thi ngay khi co.`
          : "Dang crawl tat ca nguon o che do nen. Bai moi se hien thi ngay khi co.";
      }
    } else if (status === "completed") {
      if (crawlJobText) {
        crawlJobText.textContent = "Crawl tat ca nguon da hoan tat. Dang tai lai ket qua day du.";
      }
    } else if (status === "failed") {
      if (crawlJobText) {
        crawlJobText.textContent = `Job crawl that bai: ${job.error || "Khong ro nguyen nhan"}`;
      }
    }

    if (crawlJobMeta) {
      crawlJobMeta.textContent = `Tien do ${processed}/${total} nguon · crawl thanh cong ${Number(job.crawled_source_count || 0)} · giu lai ${Number(job.article_count || 0)} bai`;
    }
  };

  const startCrawlJobPolling = () => {
    if (!crawlJobPanel) {
      return;
    }

    const jobId = (crawlJobPanel.dataset.jobId || "").trim();
    if (!jobId) {
      return;
    }

    const poll = async () => {
      try {
        const response = await fetch(`/api/crawl-jobs/${encodeURIComponent(jobId)}`, {
          headers: { Accept: "application/json" },
          cache: "no-store",
        });
        if (!response.ok) {
          if (response.status === 404 && crawlJobPollTimer) {
            clearInterval(crawlJobPollTimer);
            crawlJobPollTimer = null;
            if (crawlJobText) {
              crawlJobText.textContent = "Job crawl khong con ton tai (co the da restart dich vu).";
            }
          }
          return;
        }

        const job = await response.json();
        renderCrawlJob(job);
        if (job.status === "completed") {
          if (crawlJobPollTimer) {
            clearInterval(crawlJobPollTimer);
            crawlJobPollTimer = null;
          }
          const url = new URL(window.location.href);
          url.searchParams.set("tab", "crawl");
          url.searchParams.set("job_id", jobId);
          window.location.replace(url.toString());
          return;
        }

        if (job.status === "failed" && crawlJobPollTimer) {
          clearInterval(crawlJobPollTimer);
          crawlJobPollTimer = null;
        }
      } catch (_error) {
        // Keep polling; transient network hiccups should not stop updates.
      }
    };

    poll();
    crawlJobPollTimer = setInterval(poll, 3000);
  };

  const resultSearch = document.getElementById("result_search");
  const resultSourceFilter = document.getElementById("result_source_filter");
  const resultDateFrom = document.getElementById("result_date_from");
  const resultDateTo = document.getElementById("result_date_to");
  const resultFilterReset = document.getElementById("result_filter_reset");
  const resultCount = document.getElementById("result_count");
  const filterEmptyState = document.getElementById("filter_empty_state");
  const sourceSearch = document.getElementById("source_search");
  const sourceSearchReset = document.getElementById("source_search_reset");
  const sourceCards = Array.from(document.querySelectorAll(".entity-card"));
  const sourceFilterEmptyState = document.getElementById("source_filter_empty_state");
  const sourceBulkForm = document.getElementById("source_bulk_form");
  const sourceSelectAll = document.getElementById("source_select_all");
  const sourceBulkDeleteButton = document.getElementById("source_bulk_delete_button");
  const sourceSelectedCount = document.getElementById("source_selected_count");
  const sourceCheckboxes = Array.from(document.querySelectorAll(".source-select-checkbox"));

  const monthLookup = {
    january: 0,
    february: 1,
    march: 2,
    april: 3,
    may: 4,
    june: 5,
    july: 6,
    august: 7,
    september: 8,
    october: 9,
    november: 10,
    december: 11,
  };

  const dateOnly = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());

  const textForLanguage = (card, field, useVietnamese) => {
    const prefix = useVietnamese && card.dataset.hasVi === "true" ? "vi" : "original";
    return card.dataset[`${prefix}${field}`] || "";
  };

  const setOptionalText = (node, text, truncated = false) => {
    if (!node) {
      return;
    }

    node.textContent = text ? `${text}${truncated ? "..." : ""}` : "";
    node.hidden = !text;
  };

  const applyTranslationToggle = () => {
    const useVietnamese = Boolean(translationToggle?.checked);
    let translatedVisibleCount = 0;

    articleCards.forEach((card) => {
      const hasVietnamese = card.dataset.hasVi === "true";
      const showVietnamese = useVietnamese && hasVietnamese;
      if (showVietnamese) {
        translatedVisibleCount += 1;
      }

      const title = card.querySelector("[data-article-field='title']");
      const date = card.querySelector("[data-article-field='date']");
      const summary = card.querySelector("[data-article-field='summary']");
      const content = card.querySelector("[data-article-field='content']");
      const badge = card.querySelector("[data-translation-badge]");
      const originalView = card.querySelector("[data-original-view]");
      const prefix = showVietnamese ? "vi" : "original";

      if (title) {
        title.textContent = textForLanguage(card, "Title", showVietnamese) || title.textContent;
      }
      if (date) {
        date.textContent = textForLanguage(card, "Date", showVietnamese) || "Chưa có ngày đăng";
      }
      setOptionalText(summary, textForLanguage(card, "Summary", showVietnamese));
      setOptionalText(
        content,
        textForLanguage(card, "Content", showVietnamese),
        card.dataset[`${prefix}ContentTruncated`] === "true",
      );
      if (badge) {
        badge.hidden = !showVietnamese;
      }
      if (originalView) {
        originalView.hidden = !showVietnamese;
      }
    });

    if (translationNotice) {
      translationNotice.hidden = !useVietnamese || translatedVisibleCount === 0;
    }
  };

  const parseDateValue = (value) => {
    const raw = (value || "").trim();
    if (!raw) {
      return null;
    }

    const isoMatch = raw.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
    if (isoMatch) {
      return dateOnly(new Date(Number(isoMatch[1]), Number(isoMatch[2]) - 1, Number(isoMatch[3])));
    }

    const vnMatch = raw.match(/(?:ngày\s*)?(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})/i);
    if (vnMatch) {
      return dateOnly(new Date(Number(vnMatch[3]), Number(vnMatch[2]) - 1, Number(vnMatch[1])));
    }

    const slashMatch = raw.match(/(\d{1,2})[/-](\d{1,2})[/-](\d{4})/);
    if (slashMatch) {
      return dateOnly(new Date(Number(slashMatch[3]), Number(slashMatch[2]) - 1, Number(slashMatch[1])));
    }

    const monthMatch = raw.match(
      /(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})/i,
    );
    if (monthMatch) {
      return dateOnly(new Date(Number(monthMatch[3]), monthLookup[monthMatch[1].toLowerCase()], Number(monthMatch[2])));
    }

    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) {
      return dateOnly(parsed);
    }

    return null;
  };

  const ensureSourceFilterOptions = () => {
    if (!resultSourceFilter || !articleCards.length) {
      return;
    }

    const existingValues = new Set(Array.from(resultSourceFilter.options).map((option) => option.value));
    articleCards.forEach((card) => {
      const sourceKey = card.dataset.sourceKey || "";
      if (!sourceKey || existingValues.has(sourceKey)) {
        return;
      }

      const option = document.createElement("option");
      option.value = sourceKey;
      option.textContent = card.dataset.sourceName || sourceKey;
      resultSourceFilter.append(option);
      existingValues.add(sourceKey);
    });
  };

  const applyResultFilters = () => {
    if (!articleCards.length) {
      return;
    }

    const query = (resultSearch?.value || "").trim().toLowerCase();
    const selectedSource = resultSourceFilter?.value || "";
    const fromDate = parseDateValue(resultDateFrom?.value || "");
    const toDate = parseDateValue(resultDateTo?.value || "");
    let visibleCount = 0;

    articleCards.forEach((card) => {
      const text = card.textContent.toLowerCase();
      const cardSource = card.dataset.sourceKey || "";
      const cardDate = parseDateValue(card.dataset.publishedAt || "");
      let isVisible = true;

      if (query && !text.includes(query)) {
        isVisible = false;
      }

      if (selectedSource && cardSource !== selectedSource) {
        isVisible = false;
      }

      if ((fromDate || toDate) && !cardDate) {
        isVisible = false;
      }

      if (fromDate && cardDate && cardDate < fromDate) {
        isVisible = false;
      }

      if (toDate && cardDate && cardDate > toDate) {
        isVisible = false;
      }

      card.hidden = !isVisible;
      if (isVisible) {
        visibleCount += 1;
      }
    });

    if (resultCount) {
      resultCount.textContent = `${visibleCount}/${articleCards.length} bài đang hiển thị`;
    }

    if (filterEmptyState) {
      filterEmptyState.hidden = visibleCount > 0;
    }
  };

  ensureSourceFilterOptions();

  [resultSearch, resultSourceFilter, resultDateFrom, resultDateTo].forEach((control) => {
    if (control) {
      control.addEventListener("input", applyResultFilters);
      control.addEventListener("change", applyResultFilters);
    }
  });

  if (resultFilterReset) {
    resultFilterReset.addEventListener("click", () => {
      if (resultSearch) {
        resultSearch.value = "";
      }
      if (resultSourceFilter) {
        resultSourceFilter.value = "";
      }
      if (resultDateFrom) {
        resultDateFrom.value = "";
      }
      if (resultDateTo) {
        resultDateTo.value = "";
      }
      applyResultFilters();
    });
  }

  if (translationToggle) {
    translationToggle.addEventListener("change", () => {
      applyTranslationToggle();
      applyResultFilters();
    });
  }

  applyTranslationToggle();
  applyResultFilters();
  startCrawlJobPolling();

  const visibleSourceCheckboxes = () => sourceCheckboxes.filter((checkbox) => {
    const card = checkbox.closest(".entity-card");
    return card && !card.hidden;
  });

  const updateSourceBulkState = () => {
    if (!sourceCheckboxes.length) {
      return;
    }

    const selectedCount = sourceCheckboxes.filter((checkbox) => checkbox.checked).length;
    const visibleCheckboxes = visibleSourceCheckboxes();
    const selectedVisibleCount = visibleCheckboxes.filter((checkbox) => checkbox.checked).length;

    if (sourceBulkDeleteButton) {
      sourceBulkDeleteButton.disabled = selectedCount === 0;
    }
    if (sourceSelectedCount) {
      sourceSelectedCount.textContent = selectedCount
        ? `Đã chọn ${selectedCount} nguồn`
        : "Chưa chọn nguồn nào";
    }
    if (sourceSelectAll) {
      sourceSelectAll.checked = visibleCheckboxes.length > 0 && selectedVisibleCount === visibleCheckboxes.length;
      sourceSelectAll.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < visibleCheckboxes.length;
    }
  };

  const applySourceSearch = () => {
    if (!sourceSearch || !sourceCards.length) {
      updateSourceBulkState();
      return;
    }

    const query = sourceSearch.value.trim().toLowerCase();
    let visibleCount = 0;

    sourceCards.forEach((card) => {
      const isVisible = !query || card.textContent.toLowerCase().includes(query);
      card.hidden = !isVisible;
      if (isVisible) {
        visibleCount += 1;
      }
    });

    if (sourceFilterEmptyState) {
      sourceFilterEmptyState.hidden = visibleCount > 0;
    }
    updateSourceBulkState();
  };

  sourceCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", updateSourceBulkState);
  });

  if (sourceSelectAll) {
    sourceSelectAll.addEventListener("change", () => {
      visibleSourceCheckboxes().forEach((checkbox) => {
        checkbox.checked = sourceSelectAll.checked;
      });
      updateSourceBulkState();
    });
  }

  if (sourceBulkForm) {
    sourceBulkForm.addEventListener("submit", (event) => {
      const action = event.submitter?.value || "";
      if (action !== "delete_sources") {
        return;
      }

      const selectedCount = sourceCheckboxes.filter((checkbox) => checkbox.checked).length;
      if (!selectedCount) {
        event.preventDefault();
        updateSourceBulkState();
        return;
      }

      const confirmed = window.confirm(`Xoá ${selectedCount} nguồn đã chọn?`);
      if (!confirmed) {
        event.preventDefault();
      }
    });
  }

  if (sourceSearch) {
    sourceSearch.addEventListener("input", applySourceSearch);
    sourceSearch.addEventListener("change", applySourceSearch);
  }

  if (sourceSearchReset) {
    sourceSearchReset.addEventListener("click", () => {
      if (sourceSearch) {
        sourceSearch.value = "";
        sourceSearch.focus();
      }
      applySourceSearch();
    });
  }

  applySourceSearch();
  updateSourceBulkState();

  // Check duplicate sources realtime in source form.
  const sourceForm = document.querySelector("input[name='source_key']")?.closest("form");
  if (!sourceForm) {
    return;
  }

  const urlInput = sourceForm.querySelector("input[name='target_url']");
  const keyInput = sourceForm.querySelector("input[name='source_key']");
  const originalKeyInput = sourceForm.querySelector("input[name='original_source_key']");
  if (!urlInput || !keyInput) {
    return;
  }

  const warningDiv = document.createElement("div");
  warningDiv.className = "notice is-warning";
  warningDiv.style.display = "none";
  sourceForm.appendChild(warningDiv);

  const checkDuplicate = () => {
    const url = urlInput.value.trim().toLowerCase();
    const key = keyInput.value.trim().toLowerCase();
    const originalKey = (originalKeyInput?.value || "").trim().toLowerCase();
    const warnings = [];

    sources.forEach((source) => {
      const sourceKey = String(source.source_key || "").trim().toLowerCase();
      const sourceUrl = String(source.target_url || "").trim().toLowerCase();
      const isCurrentSource = originalKey && sourceKey === originalKey;

      if (!isCurrentSource && key && sourceKey === key) {
        warnings.push(`Key đã tồn tại: ${source.source_key}`);
      }
      if (!isCurrentSource && url && sourceUrl === url) {
        warnings.push(`URL đã tồn tại ở nguồn: ${source.name}`);
      }
    });

    if (warnings.length) {
      warningDiv.innerHTML = `<p>${warnings.join(". ")}</p>`;
      warningDiv.style.display = "block";
      return;
    }

    warningDiv.style.display = "none";
    warningDiv.innerHTML = "";
  };

  urlInput.addEventListener("input", checkDuplicate);
  keyInput.addEventListener("input", checkDuplicate);
});
