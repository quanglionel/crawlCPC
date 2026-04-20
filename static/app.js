document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("crawl-form");
  const submitButton = document.getElementById("submit_button");
  const sourceSelect = document.getElementById("selected_source_key");
  const sourceHint = document.getElementById("selected_source_hint");
  const crawlJobPanel = document.getElementById("crawl_job_panel");
  const crawlJobText = document.getElementById("crawl_job_text");
  const crawlJobMeta = document.getElementById("crawl_job_meta");
  const crawlJobProgress = document.getElementById("crawl_job_progress");
  const sources = window.SOURCE_CATALOG || [];
  const presetLabels = window.PRESET_LABELS || {};
  const sourceLookup = Object.fromEntries(sources.map((source) => [source.source_key, source]));
  const allSourcesKey = "__all__";
  let crawlJobPollTimer = null;
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

  const renderCrawlJob = (job) => {
    if (!crawlJobPanel || !job) {
      return;
    }

    crawlJobPanel.hidden = false;
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
          ? `Dang crawl: ${currentSource}`
          : "Dang crawl tat ca nguon o che do nen...";
      }
    } else if (status === "completed") {
      if (crawlJobText) {
        crawlJobText.textContent = "Crawl tat ca nguon da hoan tat, dang tai ket qua.";
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

  startCrawlJobPolling();

  const articleCards = Array.from(document.querySelectorAll(".article-card"));
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
  const summaryTransferButtons = Array.from(document.querySelectorAll(".summary-transfer-button"));
  const summaryForm = document.getElementById("summary_form");
  const summaryTitleInput = document.getElementById("summary_article_title");
  const summaryUrlInput = document.getElementById("summary_article_url");
  const summarySourceInput = document.getElementById("summary_article_source");
  const summaryDateInput = document.getElementById("summary_article_date");
  const summaryContentInput = document.getElementById("summary_article_content");
  const summaryPromptInput = document.getElementById("summary_prompt");
  const summarySubmitButton = document.getElementById("summary_submit_button");
  const summaryResetPromptButton = document.getElementById("summary_reset_prompt_button");
  const summaryClearButton = document.getElementById("summary_clear_button");
  const summaryChatThread = document.getElementById("summary_chat_thread");
  const summaryEmptyState = document.getElementById("summary_empty_state");
  const defaultSummaryPrompt = window.DEFAULT_SUMMARY_PROMPT || "";
  const summaryStorageKey = "mediaCrawler.summaryArticle";
  let activeSummaryArticle = null;

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

  applyResultFilters();

  const applySourceSearch = () => {
    if (!sourceSearch || !sourceCards.length) {
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
  };

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

  const setSummaryEmptyState = () => {
    if (!summaryEmptyState || !summaryChatThread) {
      return;
    }

    summaryEmptyState.hidden = Boolean(activeSummaryArticle) || summaryChatThread.children.length > 0;
  };

  const appendChatMessage = (role, text) => {
    if (!summaryChatThread) {
      return null;
    }

    const message = document.createElement("article");
    message.className = `chat-message is-${role}`;
    const label = document.createElement("span");
    label.className = "chat-role";
    label.textContent = role === "assistant" ? "Gemini" : role === "error" ? "Lỗi" : "Bạn";
    const body = document.createElement("div");
    body.className = "chat-body";
    body.textContent = text;
    message.append(label, body);
    summaryChatThread.append(message);
    summaryChatThread.scrollTop = summaryChatThread.scrollHeight;
    setSummaryEmptyState();
    return body;
  };

  const fillSummaryForm = (article) => {
    if (!article) {
      return;
    }

    activeSummaryArticle = article;
    if (summaryTitleInput) {
      summaryTitleInput.value = article.title || "";
    }
    if (summaryUrlInput) {
      summaryUrlInput.value = article.url || "";
    }
    if (summarySourceInput) {
      summarySourceInput.value = article.source_name || "";
    }
    if (summaryDateInput) {
      summaryDateInput.value = article.published_at || "";
    }
    if (summaryContentInput) {
      summaryContentInput.value = article.content || article.summary || "";
    }
    if (summaryPromptInput && !summaryPromptInput.value.trim()) {
      summaryPromptInput.value = defaultSummaryPrompt;
    }

    setSummaryEmptyState();
  };

  summaryTransferButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest(".article-card");
      const payloadScript = card?.querySelector(".article-transfer-payload");
      if (!payloadScript) {
        return;
      }

      try {
        const article = JSON.parse(payloadScript.textContent || "{}");
        localStorage.setItem(summaryStorageKey, JSON.stringify(article));
        const url = new URL(window.location.href);
        url.searchParams.set("tab", "summary");
        window.location.href = url.toString();
      } catch (_error) {
        button.textContent = "Không đọc được bài";
      }
    });
  });

  if (summaryForm) {
    try {
      const savedArticle = JSON.parse(localStorage.getItem(summaryStorageKey) || "null");
      if (savedArticle) {
        fillSummaryForm(savedArticle);
        appendChatMessage("user", `Đã nạp bài: ${savedArticle.title || savedArticle.url || "Bài viết"}`);
      }
    } catch (_error) {
      localStorage.removeItem(summaryStorageKey);
    }

    if (summaryPromptInput && !summaryPromptInput.value.trim()) {
      summaryPromptInput.value = defaultSummaryPrompt;
    }

    summaryForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const article = {
        source_name: summarySourceInput?.value || "",
        published_at: summaryDateInput?.value || "",
        url: summaryUrlInput?.value || "",
        title: summaryTitleInput?.value || "",
        summary: activeSummaryArticle?.summary || "",
        content: summaryContentInput?.value || "",
      };
      const prompt = summaryPromptInput?.value || defaultSummaryPrompt;

      if (!article.title.trim() && !article.content.trim()) {
        appendChatMessage("error", "Chưa có tiêu đề hoặc nội dung bài viết để tóm tắt.");
        return;
      }

      activeSummaryArticle = article;
      localStorage.setItem(summaryStorageKey, JSON.stringify(article));
      appendChatMessage("user", `Tóm tắt bài: ${article.title || article.url || "Bài viết"}`);
      const loadingBody = appendChatMessage("assistant", "Đang tóm tắt...");

      if (summarySubmitButton) {
        summarySubmitButton.disabled = true;
        summarySubmitButton.textContent = "Đang gửi...";
      }

      try {
        const response = await fetch("/api/summarize", {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ article, prompt }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Không tóm tắt được bài viết.");
        }
        if (loadingBody) {
          loadingBody.textContent = payload.summary || "";
        }
      } catch (error) {
        if (loadingBody) {
          loadingBody.textContent = error.message || "Không tóm tắt được bài viết.";
          loadingBody.closest(".chat-message")?.classList.add("is-error");
        }
      } finally {
        if (summarySubmitButton) {
          summarySubmitButton.disabled = false;
          summarySubmitButton.textContent = "Gửi tóm tắt";
        }
      }
    });
  }

  if (summaryResetPromptButton && summaryPromptInput) {
    summaryResetPromptButton.addEventListener("click", () => {
      summaryPromptInput.value = defaultSummaryPrompt;
      summaryPromptInput.focus();
    });
  }

  if (summaryClearButton) {
    summaryClearButton.addEventListener("click", () => {
      activeSummaryArticle = null;
      localStorage.removeItem(summaryStorageKey);
      [summaryTitleInput, summaryUrlInput, summarySourceInput, summaryDateInput, summaryContentInput].forEach((input) => {
        if (input) {
          input.value = "";
        }
      });
      if (summaryChatThread) {
        summaryChatThread.innerHTML = "";
      }
      setSummaryEmptyState();
    });
  }

  setSummaryEmptyState();

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
