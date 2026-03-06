from django.urls import path
from . import views

urlpatterns = [
    path('regions/',              views.RegionListView.as_view(),   name='region-list'),
    path('regions/add/',          views.RegionCreateView.as_view(), name='region-add'),
    path('regions/<slug:slug>/edit/', views.RegionUpdateView.as_view(), name='region-edit'),

    path('stores/',               views.StoreListView.as_view(),    name='store-list'),
    path('stores/add/',           views.StoreCreateView.as_view(),  name='store-add'),
    path('stores/<slug:slug>/',   views.StoreDetailView.as_view(),  name='store-detail'),
    path('stores/<slug:slug>/edit/', views.StoreUpdateView.as_view(), name='store-edit'),

    path('transfers/',            views.TransferListView.as_view(),  name='transfer-list'),
    path('transfers/new/',        views.TransferCreateView.as_view(), name='transfer-new'),
]