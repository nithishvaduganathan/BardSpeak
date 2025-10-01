// Shakespeare Club - Gamified Communication App JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize gamified features
    // Skip copy-prevention on admin pages
    const isAdminPage = document.body && document.body.classList && document.body.classList.contains('admin-page');
    if (!isAdminPage) {
        initializeCopyPrevention();
    }
    initializeAlertAutoDismiss();
    initializeModuleAnimations();
    initializeCelebrations();
});

// Prevent copy-paste functionality
function initializeCopyPrevention() {
    // Disable right-click context menu
    document.addEventListener('contextmenu', function(e) {
        if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') {
            e.preventDefault();
            showFlashMessage('Right-click disabled. Please type your response! ⌨️', 'warning');
            return false;
        }
    });

    // Disable common keyboard shortcuts for copy-paste
    document.addEventListener('keydown', function(e) {
        // Disable Ctrl+C, Ctrl+V, Ctrl+A, Ctrl+X, Ctrl+S only in input fields
        if ((e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') && 
            e.ctrlKey && (e.keyCode === 67 || e.keyCode === 86 || e.keyCode === 65 || e.keyCode === 88 || e.keyCode === 83)) {
            e.preventDefault();
            showFlashMessage('Copy-paste shortcuts disabled! Please type your response! ⌨️', 'warning');
            return false;
        }
        
        // Disable F12 (Developer Tools)
        if (e.keyCode === 123) {
            e.preventDefault();
            showFlashMessage('Developer tools disabled!', 'warning');
            return false;
        }
    });

    // Add no-copy class to input fields
    const inputs = document.querySelectorAll('textarea, input[type="text"]');
    inputs.forEach(input => {
        input.classList.add('no-copy');
        
        // Disable paste event
        input.addEventListener('paste', function(e) {
            e.preventDefault();
            showFlashMessage('🚫 Pasting is not allowed! Please type your response! ✍️', 'warning');
            return false;
        });
        
        // Disable drag and drop
        input.addEventListener('drop', function(e) {
            e.preventDefault();
            showFlashMessage('🚫 Drag and drop disabled! Please type your response!', 'warning');
            return false;
        });
        
        // Monitor for rapid typing (potential paste detection)
        let lastKeyTime = 0;
        let keyCount = 0;
        
        input.addEventListener('keydown', function(e) {
            const currentTime = Date.now();
            if (currentTime - lastKeyTime < 50) {
                keyCount++;
                if (keyCount > 10) {
                    // Potential paste detected
                    input.value = '';
                    showFlashMessage('🚫 Potential paste detected! Please type slowly and naturally!', 'warning');
                    keyCount = 0;
                }
            } else {
                keyCount = 0;
            }
            lastKeyTime = currentTime;
        });
    });
}

// Auto-dismiss alerts after 5 seconds
function initializeAlertAutoDismiss() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => {
                alert.remove();
            }, 300);
        }, 5000);
    });
}

// Module card animations
function initializeModuleAnimations() {
    const moduleCards = document.querySelectorAll('.module-card, .feature-item');
    
    moduleCards.forEach((card, index) => {
        // Stagger animation timing
        card.style.animationDelay = `${index * 0.1}s`;
        
        // Add hover sound effect (visual feedback)
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-5px) scale(1.02)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });
}

// Celebration animations
function initializeCelebrations() {
    // Check if there's a celebration trigger in the URL or session
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('celebrate') === 'true') {
        triggerCelebration();
    }
}

// Show flash message
function showFlashMessage(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} game-alert alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" style="filter: invert(1);"></button>
    `;
    
    const container = document.querySelector('.container, .container-fluid');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

// Trigger celebration animation
function triggerCelebration(points = 10, streak = 0) {
    // Create celebration overlay
    const overlay = document.createElement('div');
    overlay.className = 'celebration-overlay';
    document.body.appendChild(overlay);
    
    // Create success message
    const successMsg = document.createElement('div');
    successMsg.className = 'success-message';
    successMsg.innerHTML = `🎉 AMAZING! +${points} Points! 🎉`;
    document.body.appendChild(successMsg);
    
    // Create floating hearts and flowers (more elements for celebration)
    for (let i = 0; i < 30; i++) {
        setTimeout(() => {
            createFloatingElement();
        }, i * 80);
    }
    
    // Create screen-wide flower/heart shower
    createFlowerShower();
    
    // Play applause sound effect (visual representation)
    createApplauseEffect();
    
    // Add streak celebration if applicable
    if (streak > 1) {
        setTimeout(() => {
            showStreakCelebration(streak);
        }, 1000);
    }
    
    // Remove celebration elements after animation
    setTimeout(() => {
        overlay.remove();
        successMsg.remove();
    }, 4000);
}

// Create a shower of flowers and hearts
function createFlowerShower() {
    for (let i = 0; i < 15; i++) {
        setTimeout(() => {
            const flower = document.createElement('div');
            flower.style.position = 'fixed';
            flower.style.top = '-50px';
            flower.style.left = Math.random() * window.innerWidth + 'px';
            flower.style.fontSize = '2rem';
            flower.style.zIndex = '10000';
            flower.style.animation = 'flowerFall 3s linear forwards';
            flower.innerHTML = ['🌸', '🌺', '💖', '💕', '🌹', '🌻'][Math.floor(Math.random() * 6)];
            
            document.body.appendChild(flower);
            
            setTimeout(() => {
                flower.remove();
            }, 3000);
        }, i * 100);
    }
}

// Show streak celebration
function showStreakCelebration(streak) {
    const streakMsg = document.createElement('div');
    streakMsg.style.position = 'fixed';
    streakMsg.style.top = '70%';
    streakMsg.style.left = '50%';
    streakMsg.style.transform = 'translate(-50%, -50%)';
    streakMsg.style.background = 'linear-gradient(135deg, #e67e22 0%, #d35400 100%)';
    streakMsg.style.color = 'white';
    streakMsg.style.padding = '15px 30px';
    streakMsg.style.borderRadius = '20px';
    streakMsg.style.fontSize = '1.1rem';
    streakMsg.style.fontWeight = 'bold';
    streakMsg.style.zIndex = '10001';
    streakMsg.style.animation = 'streakPop 2s ease-out forwards';
    streakMsg.innerHTML = `🔥 ${streak} Day Streak! Keep it up! 🔥`;
    
    document.body.appendChild(streakMsg);
    
    setTimeout(() => {
        streakMsg.remove();
    }, 2000);
}

// Create floating celebration elements
function createFloatingElement() {
    const elements = ['🌸', '🌺', '💖', '💕', '⭐', '✨', '🎊', '🎉'];
    const element = document.createElement('div');
    element.className = Math.random() > 0.5 ? 'floating-heart' : 'floating-flower';
    element.innerHTML = elements[Math.floor(Math.random() * elements.length)];
    element.style.left = Math.random() * 100 + '%';
    element.style.top = Math.random() * 100 + '%';
    
    document.querySelector('.celebration-overlay').appendChild(element);
    
    // Remove element after animation
    setTimeout(() => {
        element.remove();
    }, 3000);
}

// Visual applause effect
function createApplauseEffect() {
    const applauseDiv = document.createElement('div');
    applauseDiv.style.position = 'fixed';
    applauseDiv.style.top = '20px';
    applauseDiv.style.right = '20px';
    applauseDiv.style.fontSize = '2rem';
    applauseDiv.style.zIndex = '10001';
    applauseDiv.innerHTML = '👏 👏 👏';
    applauseDiv.style.animation = 'applauseBounce 1s ease-in-out 3';
    
    document.body.appendChild(applauseDiv);
    
    setTimeout(() => {
        applauseDiv.remove();
    }, 3000);
}

// Speech recognition simulation for speaking module
function startSpeechRecognition(callback) {
    // Simulate speech recognition (in real app would use Web Speech API)
    showFlashMessage('🎤 Recording started! Read the biography aloud...', 'info');
    
    // Simulate recording for 5 seconds
    setTimeout(() => {
        showFlashMessage('✅ Recording completed! Processing...', 'success');
        
        // Simulate processing
        setTimeout(() => {
            const simulatedText = "This is a simulated transcription of the user's speech.";
            callback(simulatedText);
        }, 2000);
    }, 5000);
}

// Audio playback for listening module
function playAudio(audioFile) {
    // In a real app, this would play the actual audio file
    showFlashMessage('🔊 Audio is playing... Listen carefully!', 'info');
    
    // Simulate audio duration
    setTimeout(() => {
        showFlashMessage('🎵 Audio finished. Now type what you heard!', 'success');
    }, 10000);
}

// Form submission with gamification
function submitPracticeForm(form, moduleType) {
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    
    // Show loading state
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';
    submitBtn.disabled = true;
    
    // Simulate API call delay
    setTimeout(() => {
        submitBtn.innerHTML = originalText;
        submitBtn.disabled = false;
    }, 2000);
}

// Points animation
function animatePointsGain(points, element) {
    const pointsElement = document.createElement('div');
    pointsElement.innerHTML = `+${points} points!`;
    pointsElement.style.position = 'absolute';
    pointsElement.style.color = '#f1c40f';
    pointsElement.style.fontWeight = 'bold';
    pointsElement.style.fontSize = '1.2rem';
    pointsElement.style.zIndex = '1000';
    pointsElement.style.animation = 'pointsFloat 2s ease-out forwards';
    
    if (element) {
        element.appendChild(pointsElement);
        setTimeout(() => {
            pointsElement.remove();
        }, 2000);
    }
}

// Streak celebration
function celebrateStreak(streakDays) {
    if (streakDays >= 7) {
        triggerCelebration(50);
        showFlashMessage(`🔥 Amazing! ${streakDays} day streak! You're on fire!`, 'success');
    } else if (streakDays >= 3) {
        showFlashMessage(`🔥 Great streak! ${streakDays} days in a row!`, 'success');
    }
}

// Badge unlock animation
function unlockBadge(badgeName) {
    const badgeDiv = document.createElement('div');
    badgeDiv.className = 'badge-unlock-animation';
    badgeDiv.style.position = 'fixed';
    badgeDiv.style.top = '50%';
    badgeDiv.style.left = '50%';
    badgeDiv.style.transform = 'translate(-50%, -50%)';
    badgeDiv.style.background = 'linear-gradient(135deg, #f1c40f 0%, #f39c12 100%)';
    badgeDiv.style.color = 'white';
    badgeDiv.style.padding = '20px 30px';
    badgeDiv.style.borderRadius = '20px';
    badgeDiv.style.fontSize = '1.3rem';
    badgeDiv.style.fontWeight = 'bold';
    badgeDiv.style.zIndex = '10000';
    badgeDiv.style.animation = 'badgeUnlock 3s ease-out forwards';
    badgeDiv.innerHTML = `🏆 Badge Unlocked: ${badgeName}!`;
    
    document.body.appendChild(badgeDiv);
    
    setTimeout(() => {
        badgeDiv.remove();
    }, 3000);
}

// Leaderboard update animation
function animateLeaderboardUpdate() {
    const leaderboardRows = document.querySelectorAll('.leaderboard-row');
    leaderboardRows.forEach((row, index) => {
        row.style.animation = `slideInLeft 0.5s ease-out ${index * 0.1}s forwards`;
    });
}

// Robot character animation for listening module
function animateRobot(action = 'speak') {
    const robot = document.querySelector('.robot-character');
    if (robot) {
        if (action === 'speak') {
            robot.style.animation = 'robotSpeak 0.5s ease-in-out 3';
        } else if (action === 'listen') {
            robot.style.animation = 'robotListen 1s ease-in-out infinite';
        }
    }
}

// Add custom CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes applauseBounce {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.2); }
    }
    
    @keyframes pointsFloat {
        0% { opacity: 1; transform: translateY(0); }
        100% { opacity: 0; transform: translateY(-50px); }
    }
    
    @keyframes badgeUnlock {
        0% { opacity: 0; transform: translate(-50%, -50%) scale(0); }
        50% { opacity: 1; transform: translate(-50%, -50%) scale(1.1); }
        100% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    }
    
    @keyframes slideInLeft {
        0% { opacity: 0; transform: translateX(-50px); }
        100% { opacity: 1; transform: translateX(0); }
    }
    
    @keyframes robotSpeak {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
    }
    
    @keyframes robotListen {
        0%, 100% { transform: rotate(-5deg); }
        50% { transform: rotate(5deg); }
    }
`;
document.head.appendChild(style);