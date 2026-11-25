package org.telegram.messenger.forkgram

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.graphics.Canvas
import android.view.View
import android.view.ViewTreeObserver
import android.view.animation.AccelerateDecelerateInterpolator
import android.widget.FrameLayout
import androidx.core.util.Consumer
import org.telegram.messenger.AndroidUtilities
import org.telegram.messenger.LocaleController
import org.telegram.messenger.R
import org.telegram.ui.ActionBar.Theme
import org.telegram.ui.Components.Bulletin
import java.util.function.DoubleSupplier
import kotlin.math.abs
import kotlin.math.roundToLong

object PhotoBinBulletin {
    @JvmStatic
    fun show(container: FrameLayout, resourcesProvider: Theme.ResourcesProvider?, tag: Int, composeTop: DoubleSupplier) {
        val layout = ComposeLayout(container, resourcesProvider, composeTop)
        layout.setAnimation(R.raw.ic_delete, 36, 36)
        layout.textView.setText(LocaleController.getString(R.string.DeleteFromDeviceMessage))
        layout.textView.setSingleLine(false)
        layout.textView.maxLines = 2
        layout.imageView.translationY = AndroidUtilities.dp(1f).toFloat()
        Bulletin.make(container, layout, Bulletin.DURATION_LONG).setTag(tag).useLayoutExitTransition().show()
    }

    private class ComposeLayout(
        container: FrameLayout,
        resourcesProvider: Theme.ResourcesProvider?,
        private val composeTop: DoubleSupplier
    ) : Bulletin.LottieLayout(container.context, resourcesProvider) {
        private var reveal = 1f
        private var animator: ValueAnimator? = null
        private val parentLocation = IntArray(2)
        private val positionListener = ViewTreeObserver.OnPreDrawListener {
            updatePosition()
            true
        }

        override fun onAttachedToWindow() {
            super.onAttachedToWindow()
            viewTreeObserver.addOnPreDrawListener(positionListener)
        }

        override fun onDetachedFromWindow() {
            viewTreeObserver.removeOnPreDrawListener(positionListener)
            animator?.cancel()
            super.onDetachedFromWindow()
        }

        private fun edgeInParent(): Float {
            val host = parent as? View ?: return Float.NaN
            val edge = composeTop.asDouble.toFloat()
            if (!edge.isFinite()) return Float.NaN
            host.getLocationOnScreen(parentLocation)
            return edge - parentLocation[1] + host.scrollY
        }

        override fun updatePosition() {
            val edge = edgeInParent()
            if (!edge.isFinite() || height == 0) return
            val paintedBottom = measuredBackgroundHeight - paddingBottom
            val paintedHeight = paintedBottom - paddingTop
            val restingGap = AndroidUtilities.dp(12f)
            translationY = edge - getTop() - paddingTop - (paintedHeight + restingGap) * reveal
        }

        override fun clipTransitionToDelegate() = false

        override fun dispatchDraw(canvas: Canvas) {
            val edge = edgeInParent()
            if (!edge.isFinite()) return
            val paintedBottom = measuredBackgroundHeight - paddingBottom
            val visibleBottom = minOf(paintedBottom.toFloat(), edge - (getTop() + translationY))
            if (visibleBottom <= paddingTop) return
            val save = canvas.save()
            canvas.clipRect(0f, paddingTop.toFloat(), width.toFloat(), visibleBottom)
            super.dispatchDraw(canvas)
            canvas.restoreToCount(save)
        }

        override fun createTransition(): Bulletin.Layout.Transition = object : Bulletin.Layout.Transition {
            override fun animateEnter(
                layout: Bulletin.Layout, startAction: Runnable?, endAction: Runnable?, onUpdate: Consumer<Float>?, bottomOffset: Int
            ) {
                setReveal(0f)
                animateReveal(1f, startAction, endAction, onUpdate)
            }

            override fun animateExit(
                layout: Bulletin.Layout, startAction: Runnable?, endAction: Runnable?, onUpdate: Consumer<Float>?, bottomOffset: Int
            ) {
                animateReveal(0f, startAction, endAction, onUpdate)
            }
        }

        private fun setReveal(value: Float) {
            reveal = value
            updatePosition()
            invalidate()
        }

        private fun animateReveal(end: Float, startAction: Runnable?, endAction: Runnable?, onUpdate: Consumer<Float>?) {
            animator?.cancel()
            animator = ValueAnimator.ofFloat(reveal, end).apply {
                duration = (260f * abs(end - reveal)).roundToLong()
                interpolator = AccelerateDecelerateInterpolator()
                addUpdateListener {
                    setReveal(it.animatedValue as Float)
                    onUpdate?.accept(translationY)
                }
                addListener(object : AnimatorListenerAdapter() {
                    private var canceled = false

                    override fun onAnimationStart(animation: Animator) {
                        startAction?.run()
                    }

                    override fun onAnimationCancel(animation: Animator) {
                        canceled = true
                    }

                    override fun onAnimationEnd(animation: Animator) {
                        if (animator === animation) animator = null
                        if (!canceled) endAction?.run()
                    }
                })
            }
            animator?.start()
        }
    }
}
