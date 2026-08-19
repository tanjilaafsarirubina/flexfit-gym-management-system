document.addEventListener('DOMContentLoaded', () => {
    console.log('FlexFit JS Initialized');
});

function showToast(message, type = 'success') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;

    const toastId = 'toast-' + Date.now();
    const bgClass = type === 'success' ? 'bg-success' : (type === 'danger' ? 'bg-danger' : 'bg-info');
    
    const toastHTML = `
        <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0 show shadow" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body font-weight-bold">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHTML);

    setTimeout(() => {
        const el = document.getElementById(toastId);
        if (el) el.remove();
    }, 4000);
}

async function handleBookingAction(classId, action, btnElement) {
    const endpoint = action === 'book' ? '/api/book_class' : '/api/cancel_booking';
    
    const originalHTML = btnElement.innerHTML;
    btnElement.disabled = true;
    btnElement.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span> Processing...`;

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ class_id: classId })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showToast(data.message, 'success');

            const spotElement = document.getElementById(`spots-count-${classId}`);
            const progressBar = document.getElementById(`progress-bar-${classId}`);
            
            if (spotElement && data.booked_count !== undefined) {
                spotElement.innerText = `${data.booked_count}/${data.max_capacity} spots`;
            }

            if (progressBar && data.booked_count !== undefined && data.max_capacity) {
                const pct = Math.min(100, Math.round((data.booked_count / data.max_capacity) * 100));
                progressBar.style.width = `${pct}%`;
            }

            const classesAttendedCount = document.getElementById('stat-classes-attended');
            if (classesAttendedCount && data.user_total_classes !== undefined) {
                classesAttendedCount.innerText = `${data.user_total_classes} Sessions`;
            }

            if (data.booked) {
                btnElement.className = 'btn btn-cancel btn-sm';
                btnElement.innerHTML = `<i class="bi bi-x-circle me-1"></i> CANCEL BOOKING`;
                btnElement.setAttribute('onclick', `handleBookingAction(${classId}, 'cancel', this)`);
            } else {
                btnElement.className = 'btn btn-book btn-sm';
                btnElement.innerHTML = `<i class="bi bi-calendar-plus me-1"></i> BOOK CLASS`;
                btnElement.setAttribute('onclick', `handleBookingAction(${classId}, 'book', this)`);
            }
        } else {
            showToast(data.message || 'An error occurred.', 'danger');
            btnElement.innerHTML = originalHTML;
        }
    } catch (err) {
        console.error('Booking API Error:', err);
        showToast('Network error. Please try again.', 'danger');
        btnElement.innerHTML = originalHTML;
    } finally {
        btnElement.disabled = false;
    }
}
