from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.db.models import Sum

from .models import Region, Store, StoreStock, StockTransfer
from .forms  import RegionForm, StoreForm, StockTransferForm


# ── Regions ──────────────────────────────────────────────────────
class RegionListView(LoginRequiredMixin, ListView):
    model = Region
    template_name = 'locations/region_list.html'
    context_object_name = 'regions'

    def get_queryset(self):
        return Region.objects.prefetch_related('stores').order_by('company', 'name')


class RegionCreateView(LoginRequiredMixin, CreateView):
    model = Region
    form_class = RegionForm
    template_name = 'locations/region_form.html'
    success_url = reverse_lazy('region-list')


class RegionUpdateView(LoginRequiredMixin, UpdateView):
    model = Region
    form_class = RegionForm
    template_name = 'locations/region_form.html'
    success_url = reverse_lazy('region-list')
    slug_field = 'slug'
    slug_url_kwarg = 'slug'


# ── Stores ───────────────────────────────────────────────────────
class StoreListView(LoginRequiredMixin, ListView):
    model = Store
    template_name = 'locations/store_list.html'
    context_object_name = 'stores'

    def get_queryset(self):
        qs = Store.objects.select_related('region').order_by('region__company', 'region__name', 'name')
        company = self.request.GET.get('company')
        region  = self.request.GET.get('region')
        if company:
            qs = qs.filter(region__company=company)
        if region:
            qs = qs.filter(region__id=region)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['regions'] = Region.objects.all()
        return ctx


class StoreCreateView(LoginRequiredMixin, CreateView):
    model = Store
    form_class = StoreForm
    template_name = 'locations/store_form.html'
    success_url = reverse_lazy('store-list')


class StoreUpdateView(LoginRequiredMixin, UpdateView):
    model = Store
    form_class = StoreForm
    template_name = 'locations/store_form.html'
    success_url = reverse_lazy('store-list')
    slug_field = 'slug'
    slug_url_kwarg = 'slug'


class StoreDetailView(LoginRequiredMixin, DetailView):
    model = Store
    template_name = 'locations/store_detail.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        store = self.get_object()
        ctx['stock_entries'] = (
            StoreStock.objects
            .filter(store=store)
            .select_related('item', 'item__category')
            .order_by('item__name')
        )
        ctx['total_units'] = ctx['stock_entries'].aggregate(t=Sum('quantity'))['t'] or 0
        return ctx


# ── Transfers ────────────────────────────────────────────────────
class TransferListView(LoginRequiredMixin, ListView):
    model = StockTransfer
    template_name = 'locations/transfer_list.html'
    context_object_name = 'transfers'
    paginate_by = 20

    def get_queryset(self):
        return StockTransfer.objects.select_related(
            'from_store', 'to_store', 'item', 'created_by'
        ).order_by('-created_at')


class TransferCreateView(LoginRequiredMixin, CreateView):
    model = StockTransfer
    form_class = StockTransferForm
    template_name = 'locations/transfer_form.html'
    success_url = reverse_lazy('transfer-list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)